#!/usr/bin/env node
/* Tests for the shared review tooling. Node only, no dependencies: node tools/test/test-tools.cjs */
'use strict';
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');
const { build } = require('../review-package.cjs');
const { runReview, normalize } = require('../review-run.cjs');

let pass = 0; const fails = [];
const t = async (name, fn) => { try { await fn(); pass++; console.log(`ok   ${name}`); } catch (e) { fails.push(name); console.log(`FAIL ${name}: ${e.message}`); } };
const assert = (c, m) => { if (!c) throw new Error(m); };
const sh = (cwd, ...a) => { const r = spawnSync('git', a, { cwd, encoding: 'utf8' }); if (r.status) throw new Error(r.stderr); return r.stdout; };

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'devtools-'));
const repo = path.join(tmp, 'repo'); fs.mkdirSync(repo);
sh(repo, 'init', '-q', '-b', 'main'); sh(repo, 'config', 'user.email', 't@example.com'); sh(repo, 'config', 'user.name', 't');
fs.mkdirSync(path.join(repo, 'src')); fs.writeFileSync(path.join(repo, 'src/label.ts'), 'export const label = "Save";\n');
sh(repo, 'add', '.'); sh(repo, 'commit', '-qm', 'base');
const clean = path.join(tmp, 'clean.sh'); fs.writeFileSync(clean, '#!/bin/sh\nexit 0\n', { mode: 0o755 });
const dirty = path.join(tmp, 'dirty.sh'); fs.writeFileSync(dirty, '#!/bin/sh\ngrep -q FAKESECRET "$1" && { echo "secret at $1"; exit 1; }\nexit 0\n', { mode: 0o755 });
const record = path.join(tmp, 'record.md'); fs.writeFileSync(record, 'Change: test\nDepth: low\n');
const opts = (x) => ({ repo, base: 'HEAD', depth: 'low', record, scanner: `${clean} {file}`, out: path.join(tmp, `out-${Math.random()}`), ...x });

(async () => {
  await t('low package holds D-rules and no CODE_REVIEW sections', () => {
    fs.writeFileSync(path.join(repo, 'src/label.ts'), 'export const label = "Save changes";\n');
    const { manifest, packageFile } = build(opts());
    const p = fs.readFileSync(packageFile, 'utf8');
    assert(manifest.status === 'ready' && manifest.sections.length === 0, 'expected ready with no sections');
    assert(/### D15/.test(p) && !/## §1 Baseline/.test(p), 'low package content wrong');
    assert(/4\.3 What the reviewer is asked to do/.test(p), 'reviewer task missing (must come from REVIEW_METHOD)');
    assert(manifest.governance.sha256.length === 64, 'governance hash missing');
  });
  await t('normal package selects base and surface sections only', () => {
    const { manifest, packageFile } = build(opts({ depth: 'normal' }));
    const p = fs.readFileSync(packageFile, 'utf8');
    assert(manifest.sections.includes('§T') && manifest.sections.includes('§3') && !manifest.sections.includes('§13'), manifest.sections.join(','));
    assert(!/## §P PHP/.test(p) && !/## §F Money/.test(p), 'unselected sections leaked');
  });
  await t('schema surface forces high: normal is refused', () => {
    fs.mkdirSync(path.join(repo, 'migrations'), { recursive: true });
    fs.writeFileSync(path.join(repo, 'migrations/001.sql'), 'ALTER TABLE t ADD COLUMN c int;\n');
    let code = 0; try { build(opts({ depth: 'normal' })); } catch (e) { code = e.code; }
    assert(code === 5, `expected exit 5, got ${code}`);
    const { manifest } = build(opts({ depth: 'high' }));
    assert(manifest.sections.includes('§S') && manifest.sections.includes('§13'), manifest.sections.join(','));
    fs.rmSync(path.join(repo, 'migrations'), { recursive: true });
  });
  await t('low is refused above the changed-line cap', () => {
    fs.writeFileSync(path.join(repo, 'src/big.ts'), Array.from({ length: 60 }, (_, i) => `export const v${i} = ${i};`).join('\n'));
    let code = 0; try { build(opts()); } catch (e) { code = e.code; }
    assert(code === 5, `expected 5, got ${code}`);
    fs.unlinkSync(path.join(repo, 'src/big.ts'));
  });
  await t('.env and key files are excluded and listed', () => {
    fs.writeFileSync(path.join(repo, '.env'), 'API_KEY=FAKESECRET\n'); fs.writeFileSync(path.join(repo, 'server.pem'), 'x\n');
    const { manifest, packageFile } = build(opts({ scanner: `${dirty} {file}` }));
    const p = fs.readFileSync(packageFile, 'utf8');
    assert(!p.includes('FAKESECRET'), '.env content reached the package');
    assert(manifest.excluded.map((e) => e.path).sort().join() === '.env,server.pem', JSON.stringify(manifest.excluded));
    fs.unlinkSync(path.join(repo, '.env')); fs.unlinkSync(path.join(repo, 'server.pem'));
  });
  await t('a secret in the transmitted material blocks and leaves nothing to send', () => {
    fs.writeFileSync(path.join(repo, 'src/label.ts'), 'export const label = "FAKESECRET";\n');
    const out = path.join(tmp, 'blocked'); let code = 0;
    try { build(opts({ scanner: `${dirty} {file}`, out })); } catch (e) { code = e.code; }
    assert(code === 3, `expected 3, got ${code}`);
    assert(!fs.existsSync(path.join(out, 'package.md')), 'package.md left behind after a block');
    assert(JSON.parse(fs.readFileSync(path.join(out, 'manifest.json'))).status === 'blocked-secret-scan', 'manifest status wrong');
  });
  await t('a scanner error fails closed', () => {
    let code = 0; try { build(opts({ scanner: `${path.join(tmp, 'missing.sh')} {file}` })); } catch (e) { code = e.code; }
    assert(code === 3, `expected 3, got ${code}`);
    fs.writeFileSync(path.join(repo, 'src/label.ts'), 'export const label = "Save changes";\n');
  });
  await t('round 2 needs a listed reason; round 3 needs owner approval', () => {
    const prior = path.join(tmp, 'prior.json'); fs.writeFileSync(prior, JSON.stringify({ findings: [{ id: 'F1', issue: 'x' }] }));
    let c1 = 0; try { build(opts({ round: '2', prior })); } catch (e) { c1 = e.code; }
    assert(c1 === 6, `round 2 without reason: ${c1}`);
    const { packageFile } = build(opts({ round: '2', prior, reason: 'material_fix' }));
    assert(/Prior round findings/.test(fs.readFileSync(packageFile, 'utf8')), 'prior findings missing');
    let c3 = 0; try { build(opts({ round: '3', prior, reason: 'material_fix' })); } catch (e) { c3 = e.code; }
    assert(c3 === 6, `round 3 without approval: ${c3}`);
  });

  const ready = build(opts({ out: path.join(tmp, 'ready') }));
  const pkgDir = path.dirname(ready.packageFile);
  const okJson = '```json\n{"verdict":"PASS","findings":[]}\n```';
  const reviewers = [{ name: 'a', model: 'm-a' }, { name: 'b', model: 'm-b' }, { name: 'c', model: 'm-c' }];
  await t('one reviewer is called on success', async () => {
    const calls = [];
    const r = await runReview({ packageDir: pkgDir, reviewers, selection: { default: 'b' }, call: async (rv) => { calls.push(rv.name); return { text: okJson }; } });
    assert(r.status === 'reviewed' && r.verdict === 'PASS' && calls.join() === 'b' && !r.substitution, JSON.stringify(r));
  });
  await t('transient failure retries, then falls back, and records the substitution', async () => {
    const calls = [];
    const r = await runReview({ packageDir: pkgDir, reviewers, selection: { default: 'a' }, retries: { max: 1, backoffMs: 1 }, isTransient: () => true,
      call: async (rv) => { calls.push(rv.name); if (rv.name === 'a') throw new Error('503'); return { text: okJson }; } });
    assert(calls.join() === 'a,a,b' && r.reviewer === 'b' && r.substitution && r.substitution.from === 'a', calls.join() + JSON.stringify(r.substitution));
  });
  await t('an unparseable response is not a pass and moves to the next reviewer', async () => {
    const r = await runReview({ packageDir: pkgDir, reviewers, selection: { default: 'a' }, call: async (rv) => ({ text: rv.name === 'a' ? 'Looks good to me!' : okJson }) });
    assert(r.reviewer === 'b' && /invalid response/.test(r.attempts[0].outcome), JSON.stringify(r.attempts));
  });
  await t('all reviewers failing is "failed", never PASS', async () => {
    const r = await runReview({ packageDir: pkgDir, reviewers, retries: { max: 0 }, call: async () => { throw new Error('down'); } });
    assert(r.status === 'failed' && r.verdict === null, JSON.stringify(r));
  });
  await t('a blocking finding makes FAIL whatever the reviewer said', () => {
    const r = normalize('```json\n{"verdict":"PASS","findings":[{"severity":"blocking","rule":"D3","issue":"default repeated"}]}\n```');
    assert(r.verdict === 'FAIL' && r.reviewer_verdict === 'PASS', JSON.stringify(r));
  });
  await t('rotation picks the next reviewer after the last one used', async () => {
    const stateFile = path.join(tmp, 'rot.json'); fs.writeFileSync(stateFile, JSON.stringify({ last: 'b' }));
    const r = await runReview({ packageDir: pkgDir, reviewers, selection: { mode: 'rotate', stateFile }, call: async () => ({ text: okJson }) });
    assert(r.reviewer === 'c' && JSON.parse(fs.readFileSync(stateFile)).last === 'c', r.reviewer);
  });
  await t('a blocked package cannot be reviewed', async () => {
    let msg = ''; try { await runReview({ packageDir: path.join(tmp, 'blocked'), reviewers, call: async () => ({ text: okJson }) }); } catch (e) { msg = e.message; }
    assert(/not "ready"/.test(msg), msg);
  });

  // scan-code.py
  const py = (args, cwd = repo) => spawnSync('python3', [path.join(__dirname, '..', 'scan-code.py'), ...args], { cwd, encoding: 'utf8' });
  await t('scan-code: TLS-off and eval are found; blocking only when configured', () => {
    fs.writeFileSync(path.join(repo, 'src/bad.ts'), 'const a = { rejectUnauthorized: false };\nconst f = eval(input);\n');
    const adv = py(['--files', 'src/bad.ts', '--json']);
    const j = JSON.parse(adv.stdout);
    assert(adv.status === 0 && j.findings.map((f) => f.rule).sort().join() === 'DC001,DC002', adv.stdout);
    const cfg = path.join(tmp, 'cfg.json'); fs.writeFileSync(cfg, JSON.stringify({ blocking: ['DC001'] }));
    const blk = py(['--files', 'src/bad.ts', '--config', cfg]);
    assert(blk.status === 1 && /BLOCKING\s+DC001/.test(blk.stdout), blk.stdout);
  });
  await t('scan-code: staged mode checks only added lines', () => {
    sh(repo, 'add', 'src/bad.ts'); sh(repo, 'commit', '-qm', 'legacy');
    fs.appendFileSync(path.join(repo, 'src/bad.ts'), 'const ok = 1;\n'); sh(repo, 'add', 'src/bad.ts');
    const j = JSON.parse(py(['--staged', '--json']).stdout);
    assert(j.findings.length === 0, JSON.stringify(j.findings));
  });
  await t('scan-code: a config default is blocking only when repeated', () => {
    const cfg = path.join(tmp, 'cfg2.json'); fs.writeFileSync(cfg, JSON.stringify({ blocking: ['DC008'] }));
    fs.writeFileSync(path.join(repo, 'src/c1.ts'), "const u = process.env.API_URL || 'http://x';\n");
    sh(repo, 'add', 'src/c1.ts');
    assert(py(['--staged', '--config', cfg]).status === 0, 'single default should be advisory');
    sh(repo, 'commit', '-qm', 'c1');
    fs.writeFileSync(path.join(repo, 'src/c2.ts'), "const v = process.env.API_URL || 'http://y';\n"); sh(repo, 'add', 'src/c2.ts');
    assert(py(['--staged', '--config', cfg]).status === 1, 'repeated default should block');
  });
  await t('scan-code: config allow needs a reason; unknown rule ids are rejected', () => {
    const cfg = path.join(tmp, 'cfg3.json'); fs.writeFileSync(cfg, JSON.stringify({ allow: [{ rule: 'DC001', path: 'x' }] }));
    assert(py(['--repo', '--config', cfg]).status === 2, 'allow without reason accepted');
    fs.writeFileSync(cfg, JSON.stringify({ blocking: ['DC999'] }));
    assert(py(['--repo', '--config', cfg]).status === 2, 'unknown id accepted');
  });

  fs.rmSync(tmp, { recursive: true, force: true });
  console.log(`\n${pass} passed, ${fails.length} failed`);
  process.exit(fails.length ? 1 : 0);
})();
