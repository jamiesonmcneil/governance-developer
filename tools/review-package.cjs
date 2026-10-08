#!/usr/bin/env node
/*
 * review-package.cjs: builds the smallest sufficient package for an independent code review, from the same
 * canonical governance the author followed (REVIEW_METHOD.md section 4.2). Generic: it knows no organization,
 * provider or credential. The consuming organization supplies its rules (--rules), its scanner (--scanner)
 * and, optionally, its own surface map (--surfaces).
 *
 * node review-package.cjs --repo <dir> --base <ref> [--head <ref>] --depth low|normal|high
 *   --record <completion-record.md> [--evidence a.txt,b.log] [--context src/a.ts,src/b.ts]
 *   [--rules "path/RULES.md#Heading,..."] [--governance-hash <org effective hash>] [--paths dir/,file,...]
 *   --scanner "<command with {file}>" --out <dir>
 *   [--round 2 --prior <result.json> --reason material_issue|material_fix|unresolved_material|gate_required|owner_requested]
 *   [--round 3 --owner-approval "<who, when, where it was given>"] [--exclude <regex,...>]
 *   [--surfaces <file>]       replace the default surface map
 *   [--surfaces-add <file>]   add the organization's surfaces, base sections and exclusions to the default map
 *
 * node review-package.cjs --sections-only 1 --repo <dir> --base <ref> [--head <ref>] --depth low|normal|high
 *   [--paths ...] [--surfaces-add <file>]
 *   prints the CODE_REVIEW sections the depth and the touched surfaces select, for the author's own review
 *   (REVIEW_METHOD.md section 3); no record, scanner or package is needed or written.
 *
 * Exit: 0 package ready; 2 usage; 3 blocked by the secret scan (nothing is left to send); 4 over the size
 * budget for the depth; 5 depth below the minimum the surfaces force; 6 a round not allowed.
 * The package is written as package.md plus manifest.json. On any block, package.md is removed.
 */
'use strict';
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { spawnSync } = require('child_process');

const DEV_DIR = path.resolve(__dirname, '..');
const DEPTHS = ['low', 'normal', 'high'];
const SCAN_TIMEOUT_MS = 120000;   // a scanner that hangs is a failed scan: the spawn error blocks the package
const ROUND2_REASONS = ['material_issue', 'material_fix', 'unresolved_material', 'gate_required', 'owner_requested'];

class PackageError extends Error { constructor(code, msg) { super(msg); this.code = code; } }

const sha256 = (s) => crypto.createHash('sha256').update(s).digest('hex');
const git = (repo, args) => {
  const r = spawnSync('git', ['-C', repo, ...args], { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
  if (r.status !== 0) throw new PackageError(2, `git ${args.join(' ')} failed: ${r.stderr.trim()}`);
  return r.stdout;
};

/** A heading's section: from the heading line to the next heading of the same or higher level. */
function section(text, match) {
  const lines = text.split('\n');
  const i = lines.findIndex((l) => /^#{1,6}\s/.test(l) && match(l.replace(/^#+\s*/, '').trim()));
  if (i < 0) return null;
  const level = lines[i].match(/^#+/)[0].length;
  let j = i + 1;
  while (j < lines.length && !(/^#{1,6}\s/.test(lines[j]) && lines[j].match(/^#+/)[0].length <= level)) j++;
  return lines.slice(i, j).join('\n').trim();
}
const readGov = (file) => fs.readFileSync(path.join(DEV_DIR, file), 'utf8');
const needSection = (file, text, match, label) => {
  const s = section(text, match);
  if (!s) throw new PackageError(2, `governance section "${label}" not found in ${file}: the canonical source changed shape`);
  return s;
};

/** Split a unified diff into per-file blocks. */
function splitDiff(diff) {
  const blocks = [];
  for (const part of diff.split(/^(?=diff --git )/m)) {
    if (!part.startsWith('diff --git ')) continue;
    const m = part.match(/^diff --git a\/(.+?) b\/(.+)$/m);
    const file = m ? m[2] : 'unknown';
    const added = (part.match(/^\+(?!\+\+)/gm) || []).length;
    const removed = (part.match(/^-(?!--)/gm) || []).length;
    blocks.push({ file, text: part.trimEnd(), added, removed });
  }
  return blocks;
}

/** The logical change's diff. `paths` (optional) limits it to the files that make up the change. */
function collectDiff(repo, base, head, paths) {
  const spec = paths && paths.length ? ['--', ...paths] : [];
  if (head) return git(repo, ['diff', '--no-color', '--no-ext-diff', '-U3', `${base}..${head}`, ...spec]);
  let d = git(repo, ['diff', '--no-color', '--no-ext-diff', '-U3', base, ...spec]);
  for (const f of git(repo, ['ls-files', '--others', '--exclude-standard', ...spec]).split('\n').filter(Boolean)) {
    const r = spawnSync('git', ['-C', repo, 'diff', '--no-color', '--no-index', '--', '/dev/null', f], { encoding: 'utf8' });
    d += `\n${r.stdout.replace(/^diff --git a\/\/dev\/null b\//m, `diff --git a/${f} b/`)}`;
  }
  return d;
}

function detectSurfaces(blocks, cfg) {
  const forced = new Set(); const signals = {}; const sections = new Set(); const surfaces = [];
  for (const [name, s] of Object.entries(cfg.surfaces)) {
    const byPath = (s.paths || []).some((re) => blocks.some((b) => new RegExp(re).test(b.file)));
    const hits = byPath ? [] : blocks.filter((b) => (s.content || []).some((re) =>
      b.text.split('\n').some((l) => l.startsWith('+') && new RegExp(re, 'i').test(l)))).map((b) => b.file);
    if (byPath) { surfaces.push(name); (s.sections || []).forEach((x) => sections.add(x)); if (s.forces) forced.add(s.forces); }
    else if (hits.length) signals[name] = hits;
  }
  return { surfaces, signals, sections: [...sections], minDepth: forced.has('high') ? 'high' : null };
}

/** The surface map: the default, or a replacement, plus any organization additions. */
function loadSurfaces(o) {
  const cfg = JSON.parse(fs.readFileSync(o.surfaces || path.join(__dirname, 'surfaces.json'), 'utf8'));
  if (o.surfacesAdd) {
    const add = JSON.parse(fs.readFileSync(o.surfacesAdd, 'utf8'));
    Object.assign(cfg.surfaces, add.surfaces || {});
    for (const [d, list] of Object.entries(add.base_sections || {})) {
      if (!DEPTHS.includes(d)) throw new PackageError(2, `--surfaces-add: unknown depth ${d} in base_sections`);
      cfg.base_sections[d] = [...new Set([...(cfg.base_sections[d] || []), ...list])];
    }
    cfg.exclude = [...cfg.exclude, ...(add.exclude || [])];
  }
  return cfg;
}

/** The touched surfaces and the CODE_REVIEW sections the depth and those surfaces select. */
function selection(o) {
  const cfg = loadSurfaces(o);
  const excl = [...cfg.exclude, ...(o.exclude || [])].map((x) => new RegExp(x, 'i'));
  const isExcluded = (f) => excl.some((x) => x.test(f));
  const all = splitDiff(collectDiff(o.repo, o.base, o.head, o.paths));
  if (!all.length) throw new PackageError(2, 'the diff is empty: nothing to review');
  const blocks = all.filter((b) => !isExcluded(b.file));
  const excluded = all.filter((b) => isExcluded(b.file)).map((b) => ({ path: b.file, reason: 'excluded by pattern (secrets, keys, environment or data files)' }));
  if (!blocks.length) throw new PackageError(2, `every changed file is excluded (${all.map((b) => b.file).join(', ')}): there is nothing reviewable to send. Review the change another way or narrow the exclusions in the organization's surfaces file`);
  const changed = blocks.reduce((n, b) => n + b.added + b.removed, 0);
  const det = detectSurfaces(blocks, cfg);
  if (det.minDepth && DEPTHS.indexOf(o.depth) < DEPTHS.indexOf(det.minDepth))
    throw new PackageError(5, `depth ${o.depth} is below ${det.minDepth}, which the touched surfaces force (${det.surfaces.join(', ')})`);
  if (o.depth === 'low' && changed > cfg.low_max_changed_lines)
    throw new PackageError(5, `depth low allows at most ${cfg.low_max_changed_lines} changed lines; this change has ${changed}`);
  const crTxt = readGov('CODE_REVIEW.md');
  const selected = o.depth === 'low' ? [] : [...new Set([...cfg.base_sections[o.depth], ...det.sections])];
  const order = (s) => { const i = crTxt.indexOf(`## ${s} `); return i < 0 ? Infinity : i; };
  selected.sort((a, b) => order(a) - order(b));
  const crSections = selected.map((s) => needSection('CODE_REVIEW.md', crTxt, (h) => h.startsWith(`${s} `), s));
  return { cfg, blocks, excluded, isExcluded, changed, det, selected, crSections };
}

/** For the author's own review: the sections to apply, with no package built. */
function sectionsOnly(o) {
  for (const k of ['repo', 'base', 'depth']) if (!o[k]) throw new PackageError(2, `--${k} is required`);
  if (!DEPTHS.includes(o.depth)) throw new PackageError(2, `--depth must be one of ${DEPTHS.join(', ')}`);
  const { det, selected, crSections, changed } = selection(o);
  return { depth: o.depth, surfaces: det.surfaces, signals: det.signals, sections: selected, changed, text: crSections.join('\n\n') };
}

function build(o) {
  for (const k of ['repo', 'base', 'depth', 'record', 'scanner', 'out']) if (!o[k]) throw new PackageError(2, `--${k} is required`);
  if (!DEPTHS.includes(o.depth)) throw new PackageError(2, `--depth must be one of ${DEPTHS.join(', ')}`);
  // The scanner must be handed the exact package file, or it would pass without reading what is sent.
  if (!/\{file\}/.test(o.scanner)) throw new PackageError(2, '--scanner must contain {file}: the scan has to read the exact package that would be transmitted');
  const round = Number(o.round || 1);
  if (round === 2 && (!o.prior || !ROUND2_REASONS.includes(o.reason)))
    throw new PackageError(6, `a second round needs --prior <result.json> and --reason one of ${ROUND2_REASONS.join(', ')} (REVIEW_METHOD 4.6)`);
  if (round >= 3 && (typeof o.ownerApproval !== 'string' || o.ownerApproval.trim().length < 10)) throw new PackageError(6, 'a third review round requires the owner\'s explicit approval, recorded as --owner-approval "<who, when, where it was given>"');
  const { cfg, blocks, excluded, isExcluded, changed, det, selected, crSections } = selection(o);

  // Governance, from the canonical sources only.
  const rulesTxt = readGov('DEVELOPER_RULES.md'); const methodTxt = readGov('REVIEW_METHOD.md');
  const verTxt = readGov('VERIFICATION.md');
  const gov = [
    needSection('DEVELOPER_RULES.md', rulesTxt, (h) => h === 'Hard rules and guidelines', 'Hard rules and guidelines'),
    needSection('DEVELOPER_RULES.md', rulesTxt, (h) => h === 'The rules', 'The rules'),
  ];
  if (o.depth !== 'low') {
    gov.push(needSection('VERIFICATION.md', verTxt, (h) => h.startsWith('2. '), 'VERIFICATION 2'));
    gov.push(needSection('VERIFICATION.md', verTxt, (h) => h.startsWith('3. '), 'VERIFICATION 3'));
  }
  const task = needSection('REVIEW_METHOD.md', methodTxt, (h) => h.startsWith('4.3 '), 'REVIEW_METHOD 4.3');
  const resultSpec = needSection('REVIEW_METHOD.md', methodTxt, (h) => h.startsWith('4.4 '), 'REVIEW_METHOD 4.4');
  const orgRules = (o.rules || []).map((ref) => {
    const [file, heading] = ref.split('#');
    const txt = fs.readFileSync(file, 'utf8');
    return heading ? needSection(file, txt, (h) => h.toLowerCase().includes(heading.toLowerCase()), ref) : txt.trim();
  });
  const govText = [...gov, task, resultSpec, ...crSections, ...orgRules].join('\n\n');
  let devCommit;
  try { devCommit = git(DEV_DIR, ['rev-parse', 'HEAD']).trim(); } catch { devCommit = null; /* not a git checkout: the sha256 below still pins the text */ }

  const readCapped = (f, cap) => { const t = fs.readFileSync(f, 'utf8'); return t.length > cap ? `${t.slice(0, cap)}\n[truncated at ${cap} characters]` : t; };
  const evidence = (o.evidence || []).map((f) => `### ${path.basename(f)}\n\n\`\`\`\n${readCapped(f, 20000)}\n\`\`\``);
  for (const f of o.context || []) {
    const abs = path.resolve(o.repo, f);
    if (!abs.startsWith(path.resolve(o.repo) + path.sep)) throw new PackageError(2, `context file ${f} is outside the repository`);
  }
  const context = (o.context || []).filter((f) => !isExcluded(f)).map((f) => `### ${f}\n\n\`\`\`\n${readCapped(path.join(o.repo, f), 40000)}\n\`\`\``);
  for (const f of (o.context || []).filter(isExcluded)) excluded.push({ path: f, reason: 'context file excluded by pattern' });
  const prior = round >= 2 ? JSON.parse(fs.readFileSync(o.prior, 'utf8')) : null;

  const parts = [
    '# Independent code review',
    'You are the independent reviewer of a completed logical code change. The author has already reviewed it against the governance below and recorded the evidence. Review the change against the supplied governance only, verify the claims against the diff and the evidence instead of accepting them, and return actionable findings, not an essay.',
    task,
    resultSpec,
    '## Output format\n\nReturn exactly one JSON object in a ```json fenced block and nothing else:\n\n```json\n{"verdict": "PASS | PASS_WITH_FINDINGS | FAIL", "findings": [{"severity": "blocking | major | minor", "rule": "D3 or a CODE_REVIEW item such as 3.5", "file": "path", "line": 0, "issue": "...", "evidence": "...", "action": "..."}]}\n```\n\nUse "blocking" only for a violation of a Hard rule or a defect that must be fixed before the change is complete. Return an empty findings array when you find nothing.',
    `## The change\n\n- Review depth: **${o.depth}**${det.surfaces.length ? ` (surfaces: ${det.surfaces.join(', ')})` : ''}\n- Changed lines: ${changed} across ${blocks.length} file(s)\n- Review round: ${round}${round >= 2 ? ` (reason: ${o.reason}; focus on the prior findings and the change since)` : ''}${Object.keys(det.signals).length ? `\n- Possible further surfaces to check (content signals, not confirmed): ${Object.entries(det.signals).map(([k, v]) => `${k} in ${v.slice(0, 3).join(', ')}`).join('; ')}` : ''}${excluded.length ? `\n- Files excluded from this package: ${excluded.map((e) => e.path).join(', ')}` : ''}`,
    `## Governance: Development Core Rules\n\n${gov.slice(0, 2).join('\n\n')}`,
    o.depth !== 'low' ? `## Governance: verification\n\n${gov.slice(2).join('\n\n')}` : '',
    crSections.length ? `## Governance: CODE_REVIEW sections for this change\n\n${crSections.join('\n\n')}` : '',
    orgRules.length ? `## Governance: organization and project rules\n\n${orgRules.join('\n\n')}` : '',
    `## Author's completion record\n\n${readCapped(o.record, 30000)}`,
    evidence.length ? `## Evidence\n\n${evidence.join('\n\n')}` : '',
    prior ? `## Prior round findings\n\n\`\`\`json\n${JSON.stringify(prior.findings || [], null, 1)}\n\`\`\`` : '',
    context.length ? `## Source context\n\n${context.join('\n\n')}` : '',
    `## Diff\n\n\`\`\`diff\n${blocks.map((b) => b.text).join('\n')}\n\`\`\``,
  ].filter(Boolean).join('\n\n');

  fs.mkdirSync(o.out, { recursive: true });
  const pkgFile = path.join(o.out, 'package.md');
  const manifest = {
    package_version: 1, created: new Date().toISOString(), repo: path.basename(path.resolve(o.repo)),
    base: o.base, head: o.head || 'working-tree', paths: o.paths || null, depth: o.depth, surfaces: det.surfaces, signals: det.signals,
    sections: selected, round, reason: o.reason || null, owner_approval: round >= 3 ? o.ownerApproval : null,
    governance: { developer_commit: devCommit, sha256: sha256(govText), org_hash: o.governanceHash || null, rules: o.rules || [] },
    files: blocks.map((b) => ({ path: b.file, added: b.added, removed: b.removed })), excluded,
    bytes: Buffer.byteLength(parts), status: 'pending-scan',
  };
  const budget = cfg.max_package_bytes[o.depth];
  if (manifest.bytes > budget) {
    manifest.status = 'blocked-size';
    fs.writeFileSync(path.join(o.out, 'manifest.json'), JSON.stringify(manifest, null, 1));
    throw new PackageError(4, `package is ${manifest.bytes} bytes, over the ${o.depth} budget of ${budget}: narrow the context or split the change`);
  }
  fs.writeFileSync(pkgFile, parts);
  // Secret-scan the exact bytes that would be transmitted. Any finding or scanner error blocks (fail closed).
  const argv = o.scanner.split(/\s+/).filter(Boolean).map((a) => a.replace('{file}', pkgFile));
  const scan = spawnSync(argv[0], argv.slice(1), { encoding: 'utf8', timeout: SCAN_TIMEOUT_MS });
  manifest.scan = { command: argv.map((a) => (a === pkgFile ? '<package>' : a)).join(' '), exit: scan.status, output: `${scan.stdout || ''}${scan.stderr || ''}${scan.error ? `scanner did not run: ${scan.error.message}` : ''}`.trim().slice(0, 4000) };
  if (scan.error || scan.status !== 0) {
    fs.unlinkSync(pkgFile);
    manifest.status = 'blocked-secret-scan';
    fs.writeFileSync(path.join(o.out, 'manifest.json'), JSON.stringify(manifest, null, 1));
    throw new PackageError(3, `secret scan blocked the package (exit ${scan.status}). Remove or exclude the content it names and rebuild:\n${manifest.scan.output}`);
  }
  manifest.status = 'ready';
  manifest.sha256 = sha256(parts);
  fs.writeFileSync(path.join(o.out, 'manifest.json'), JSON.stringify(manifest, null, 1));
  return { manifest, packageFile: pkgFile };
}

function parseArgs(argv) {
  const o = {}; const list = ['evidence', 'context', 'rules', 'paths', 'exclude'];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (!a.startsWith('--')) throw new PackageError(2, `unexpected argument ${a}`);
    const k = a.slice(2).replace(/-([a-z])/g, (_, c) => c.toUpperCase());
    const v = argv[++i];
    if (v === undefined) throw new PackageError(2, `${a} needs a value`);
    o[k] = list.includes(k) ? v.split(',').map((s) => s.trim()).filter(Boolean) : v;
  }
  return o;
}

module.exports = { build, sectionsOnly, section, splitDiff, detectSurfaces, PackageError, ROUND2_REASONS };

if (require.main === module) {
  try {
    const opts = parseArgs(process.argv.slice(2));
    if (opts.sectionsOnly) {
      const r = sectionsOnly(opts);
      console.log(`Depth ${r.depth}; ${r.changed} changed lines; surfaces: ${r.surfaces.join(', ') || 'none'}${Object.keys(r.signals).length ? `; possible (check): ${Object.keys(r.signals).join(', ')}` : ''}; sections: ${r.sections.join(' ') || 'none (Low: D1 to D15, the mechanical checks and the tests are the review)'}\n`);
      if (r.text) console.log(r.text);
      process.exit(0);
    }
    const { manifest, packageFile } = build(opts);
    console.log(`review package ready: ${packageFile} (${manifest.bytes} bytes, depth ${manifest.depth}, sections ${manifest.sections.join(' ') || 'none'})`);
  } catch (e) {
    console.error(`review-package: ${e.message}`);
    process.exit(e.code && Number.isInteger(e.code) ? e.code : 2);
  }
}
