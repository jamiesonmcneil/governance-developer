/*
 * review-run.cjs: runs one independent review of a ready package (REVIEW_METHOD.md sections 4.1, 4.4, 4.8).
 * Generic: the consuming organization injects its approved reviewers and the transport that calls them.
 *
 *   const { runReview } = require('./review-run.cjs');
 *   const out = await runReview({
 *     packageDir,                         // holds package.md and a manifest.json with status "ready"
 *     reviewers: [{ name, model }],       // approved reviewers, in fallback order
 *     selection: { mode: 'default' | 'rotate', default: 'name', stateFile },
 *     retries: { max: 2, backoffMs: 2000 },
 *     call: async (reviewer, prompt) => ({ text, usage, model }),   // throws on failure
 *     isTransient: (err) => boolean,      // timeouts, rate limits, 5xx
 *     onAttempt: async (attempt) => {},   // logging hook
 *   });
 *
 * One reviewer is called. Another is tried only when the selected one fails (bounded retries first) or
 * returns a response that cannot be normalized, and the substitution is recorded. A failure is never a pass:
 * if no reviewer succeeds, status is "failed" and verdict is null.
 */
'use strict';
const fs = require('fs');
const path = require('path');

const SEVERITIES = ['blocking', 'major', 'minor'];

/** Normalize a raw reviewer response to { verdict, reviewer_verdict, findings }. Throws if it cannot. */
function normalize(text) {
  const fenced = [...String(text).matchAll(/```json\s*([\s\S]*?)```/g)].map((m) => m[1]);
  const candidates = fenced.length ? fenced : [String(text).slice(String(text).indexOf('{'), String(text).lastIndexOf('}') + 1)];
  let obj = null;
  for (const c of candidates) { try { obj = JSON.parse(c); break; } catch { /* next */ } }
  if (!obj || typeof obj !== 'object' || !Array.isArray(obj.findings)) throw new Error('response is not the required JSON object with a findings array');
  const findings = obj.findings.map((f, i) => {
    const sev = String(f.severity || '').toLowerCase();
    if (!SEVERITIES.includes(sev)) throw new Error(`finding ${i + 1} has severity "${f.severity}", not one of ${SEVERITIES.join(', ')}`);
    if (!f.issue) throw new Error(`finding ${i + 1} has no issue text`);
    return { id: `F${i + 1}`, severity: sev, rule: f.rule || null, file: f.file || null, line: Number.isFinite(Number(f.line)) ? Number(f.line) : null, issue: String(f.issue), evidence: f.evidence ? String(f.evidence) : null, action: f.action ? String(f.action) : null };
  });
  // The verdict follows the findings, whatever the reviewer called it: a blocking finding is a FAIL.
  const verdict = findings.some((f) => f.severity === 'blocking') ? 'FAIL' : findings.length ? 'PASS_WITH_FINDINGS' : 'PASS';
  return { verdict, reviewer_verdict: obj.verdict || null, findings };
}

function order(reviewers, selection) {
  const names = reviewers.map((r) => r.name);
  if (!names.length) throw new Error('no approved reviewers configured');
  let first = selection.default && names.includes(selection.default) ? selection.default : names[0];
  if (selection.mode === 'rotate' && selection.stateFile) {
    let last = null;
    try { last = JSON.parse(fs.readFileSync(selection.stateFile, 'utf8')).last; } catch { /* first run */ }
    if (names.includes(last)) first = names[(names.indexOf(last) + 1) % names.length];
  }
  return [first, ...names.filter((n) => n !== first)].map((n) => reviewers.find((r) => r.name === n));
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function runReview(o) {
  const manifest = JSON.parse(fs.readFileSync(path.join(o.packageDir, 'manifest.json'), 'utf8'));
  if (manifest.status !== 'ready') throw new Error(`package status is "${manifest.status}", not "ready": it was not built or it was blocked`);
  const prompt = fs.readFileSync(path.join(o.packageDir, 'package.md'), 'utf8');
  const retries = { max: 2, backoffMs: 2000, ...(o.retries || {}) };
  const attempts = [];
  const ordered = order(o.reviewers, o.selection || {});
  for (const reviewer of ordered) {
    for (let n = 0; n <= retries.max; n++) {
      const started = Date.now();
      const attempt = { reviewer: reviewer.name, model: reviewer.model, try: n + 1, started: new Date(started).toISOString() };
      try {
        const r = await o.call(reviewer, prompt);
        attempt.ms = Date.now() - started; attempt.model = r.model || reviewer.model; attempt.usage = r.usage || {};
        try {
          const result = normalize(r.text);
          attempt.outcome = 'ok';
          attempts.push(attempt);
          if (o.onAttempt) await o.onAttempt({ ...attempt, raw: r.text, prompt });
          if (o.selection && o.selection.mode === 'rotate' && o.selection.stateFile) fs.writeFileSync(o.selection.stateFile, JSON.stringify({ last: reviewer.name }));
          const substituted = reviewer.name !== ordered[0].name;
          return { status: 'reviewed', ...result, reviewer: reviewer.name, model: attempt.model, round: manifest.round, depth: manifest.depth, governance: manifest.governance, package_sha256: manifest.sha256, substitution: substituted ? { from: ordered[0].name, to: reviewer.name, reason: attempts.filter((a) => a.reviewer !== reviewer.name).map((a) => `${a.reviewer} try ${a.try}: ${a.outcome}`).join('; ') } : null, attempts };
        } catch (e) {
          attempt.outcome = `invalid response: ${e.message}`;
          attempts.push(attempt);
          if (o.onAttempt) await o.onAttempt({ ...attempt, raw: r.text, prompt });
          break;                                   // a healthy reviewer that answered badly: move to the next one
        }
      } catch (e) {
        attempt.ms = Date.now() - started; attempt.outcome = `error: ${String(e.message || e).slice(0, 300)}`;
        attempts.push(attempt);
        if (o.onAttempt) await o.onAttempt({ ...attempt, raw: null, prompt });
        if (!(o.isTransient && o.isTransient(e)) || n === retries.max) break;
        await sleep(retries.backoffMs * 2 ** n);
      }
    }
  }
  return { status: 'failed', verdict: null, findings: [], reviewer: null, round: manifest.round, depth: manifest.depth, governance: manifest.governance, package_sha256: manifest.sha256, attempts, note: 'No reviewer produced a usable review. The change is not approved.' };
}

module.exports = { runReview, normalize, order };
