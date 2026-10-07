#!/usr/bin/env python3
"""
scan-code.py: deterministic code-quality checks for the shared Developer role.

Cheap, high-confidence mistakes are caught mechanically so review time goes to judgement. Every rule here is
ADVISORY unless the consuming organization's config lists it under "blocking", after measuring it against its
own repositories. A rule is never made blocking just because it exists.

Modes (exactly one):
  --staged              added lines in the git index (pre-commit)
  --diff BASE           added lines between BASE and the working tree
  --commit SHA          added lines of one commit (measurement)
  --repo                every line of every tracked file (measurement and audits)
  --files F [F ...]     every line of the named files

Options:
  --config FILE         organization config (JSON): blocking, disabled, exclude_paths, allow, thresholds,
                        safe_sql_interpolations (regexes for interpolations the project's query builder parameterizes)
  --root DIR            repository root (default: the current git top level)
  --json                machine-readable output

Exit: 0 no blocking finding, 1 at least one blocking finding, 2 usage or configuration error.
A finding is suppressed only by the organization's config (rule + path + reason), never by a code comment:
a comment is not approval (D11).
"""
import json, os, re, subprocess, sys
from collections import defaultdict

DEFAULT_EXCLUDE = [
    r'(^|/)node_modules/', r'(^|/)(dist|build|out|coverage|\.next|vendor|\.git)/', r'\.min\.(js|css)$',
    r'(^|/)(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|composer\.lock)$', r'\.(map|snap|svg|png|jpe?g|gif|ico|pdf|woff2?|ttf)$',
]
CODE = r'\.(ts|tsx|js|jsx|mjs|cjs|py|php|rb|go|java|cs|sh|bash)$'
JS = r'\.(ts|tsx|js|jsx|mjs|cjs)$'
TEST = r'(\.(test|spec)\.[a-z]+$|(^|/)(tests?|__tests__|e2e|fixtures?)/)'
DOC = r'\.(md|mdx|txt|rst)$'

# id, name, file regex, line regex, skip-path regex (or None), skip-line regex (or None), why
RULES = [
    ('DC001', 'tls-verification-disabled', CODE,
     r'rejectUnauthorized\s*:\s*false|NODE_TLS_REJECT_UNAUTHORIZED\s*=\s*[\'"]?0|\bverify\s*=\s*False\b|CURLOPT_SSL_VERIFY(PEER|HOST)\s*,\s*(false|0)\b|InsecureSkipVerify\s*:\s*true|\bcurl\b[^\n]*\s(-k|--insecure)\b',
     None, None, 'D5: TLS verification stays enabled'),
    ('DC002', 'dynamic-code-execution', CODE,
     r'(?<![\w.$])eval\s*\(|\bnew\s+Function\s*\(|\bvm\.(runIn\w+|Script)\b|(?<![\w.])exec\s*\(\s*(?![\'"])|\bcreate_function\s*\(',
     None, r'^\s*(//|#|\*)', 'D5: never dynamically execute untrusted input'),
    ('DC003', 'unsafe-deserialization', CODE,
     r'\bpickle\.loads?\s*\(|\byaml\.load\s*\((?![^)]*SafeLoader)|(?<![\w>])unserialize\s*\(|\bmarshal\.loads?\s*\(|node-serialize|\bObjectInputStream\b',
     None, r'^\s*(//|#|\*)', 'D5: never use unsafe deserialization'),
    ('DC004', 'debug-artifact', CODE,
     r'^\s*debugger\s*;?\s*$|\bvar_dump\s*\(|\bprint_r\s*\(|(?<![\w.>$])dd\s*\(|\bpdb\.set_trace\s*\(|(?<![\w.])breakpoint\s*\(\s*\)',
     TEST, r'^\s*(//|#|\*)', 'Debug artefacts are removed before commit'),
    ('DC005', 'console-log', JS, r'\bconsole\.(log|debug)\s*\(', TEST + r'|(^|/)(scripts?|tools?|bin)/', r'^\s*(//|\*)',
     'Debug output in application code'),
    ('DC006', 'localhost-endpoint', CODE, r'https?://(localhost|127\.0\.0\.1|0\.0\.0\.0)(:\d+)?\b',
     TEST + r'|(^|/)(scripts?|tools?|bin|docs?)/|(^|/)[^/]*\.config\.[a-z]+$', r'^\s*(//|#|\*)',
     'D3: runtime endpoints come from configuration'),
    ('DC007', 'private-network-literal', CODE, r'\b(10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b',
     TEST, r'^\s*(//|#|\*)', 'D3: hosts come from configuration'),
    ('DC008', 'config-default-at-call-site', CODE,
     r'process\.env\.([A-Z][A-Z0-9_]*)\s*(\|\||\?\?)\s*[\'"`\d]|os\.(?:environ\.get|getenv)\(\s*[\'"]([A-Z][A-Z0-9_]*)[\'"]\s*,\s*[\'"\d]|getenv\(\s*[\'"]([A-Z][A-Z0-9_]*)[\'"]\s*\)\s*\?:',
     TEST, r'^\s*(//|#|\*)', 'D3: a default is defined once, not repeated at call sites'),
    ('DC009', 'money-as-float', CODE,
     r'parseFloat\([^)]*(price|amount|total|cost|fee|balance)|\b(price|amount|total|cost|fee|balance)\w*\s*[*/]\s*\d+\.\d+|\.toFixed\(\s*2\s*\)',
     TEST, r'^\s*(//|#|\*)', 'D6: money uses integer minor units or fixed-precision decimal'),
    ('DC010', 'sql-string-building', CODE,
     r'`[^`]*\b(SELECT|INSERT\s+INTO|UPDATE|DELETE\s+FROM)\b[^`]*\$\{|[\'"]\s*(SELECT|INSERT\s+INTO|UPDATE|DELETE\s+FROM)\b[^\'"]*[\'"]\s*\+\s*\w',
     TEST, r'^\s*(//|#|\*)', 'D5: parameterize queries'),
    ('DC011', 'numeric-id-literal', CODE, r'[!=]==?\s*(?!(19|20)\d\d\b)\d{4,}\b|\b(?!(19|20)\d\d\b)\d{4,}\s*[!=]==?',
     TEST, r'^\s*(//|#|\*)', 'D3: identifiers come from configuration or data'),
    ('DC012', 'waiver-comment', CODE,
     r'(TODO|FIXME|HACK|XXX)\b[^\n]*(hard.?cod|temporar|for now|bypass|skip (the )?check)|eslint-disable(?:-next-line)?\s*$|@ts-(ignore|nocheck)\s*$',
     TEST, None, 'D11: a comment acknowledging a violation is not approval'),
]
ALL_IDS = [r[0] for r in RULES] + ['DC013']


def git(root, *args):
    return subprocess.run(['git', '-C', root, *args], capture_output=True, text=True, check=True).stdout


def load_config(path):
    if not path:
        return {}
    with open(path) as f:
        cfg = json.load(f)
    for rid in cfg.get('blocking', []) + cfg.get('disabled', []):
        if rid not in ALL_IDS:
            raise ValueError(f'unknown rule id in config: {rid}')
    for a in cfg.get('allow', []):
        if not a.get('reason'):
            raise ValueError(f'allow entry without a reason: {a}')
    return cfg


def added_lines(diff_text):
    """Yield (path, line_no, text) for every added line in a unified diff."""
    path, line = None, 0
    for raw in diff_text.splitlines():
        if raw.startswith('+++ '):
            p = raw[4:].strip()
            path = None if p == '/dev/null' else re.sub(r'^b/', '', p)
        elif raw.startswith('@@'):
            m = re.search(r'\+(\d+)', raw)
            line = int(m.group(1)) if m else 0
        elif path and raw.startswith('+') and not raw.startswith('+++'):
            yield path, line, raw[1:]
            line += 1
        elif path and not raw.startswith('-'):
            line += 1


def file_lines(root, paths):
    for p in paths:
        full = os.path.join(root, p)
        try:
            with open(full, encoding='utf-8', errors='replace') as f:
                for i, t in enumerate(f, 1):
                    yield p, i, t.rstrip('\n')
        except (IsADirectoryError, FileNotFoundError):
            continue


def normalize(t):
    return re.sub(r'\s+', ' ', t.strip())


def duplication(root, adds, min_lines, excluded):
    """Added blocks of >= min_lines normalized non-trivial lines that already exist verbatim elsewhere."""
    by_file = defaultdict(list)
    for p, n, t in adds:
        by_file[p].append((n, t))
    exts = {os.path.splitext(p)[1] for p in by_file if re.search(CODE, p)}
    if not exts:
        return []
    index = {}
    for p in git(root, 'ls-files').splitlines():
        if os.path.splitext(p)[1] not in exts or excluded(p) or re.search(TEST, p):
            continue
        body = [normalize(t) for _, _, t in file_lines(root, [p])]
        body = [t for t in body if len(t) > 3 and t not in ('{', '}', ');', '});')]
        for i in range(len(body) - min_lines + 1):
            index.setdefault(hash(tuple(body[i:i + min_lines])), set()).add(p)
    out = []
    for p, rows in by_file.items():
        if not re.search(CODE, p) or re.search(TEST, p):
            continue
        rows = [(n, normalize(t)) for n, t in rows if len(normalize(t)) > 3 and normalize(t) not in ('{', '}', ');', '});')]
        i = 0
        while i <= len(rows) - min_lines:
            others = index.get(hash(tuple(t for _, t in rows[i:i + min_lines])), set()) - {p}
            if others:
                out.append(('DC013', 'possible-duplication', p, rows[i][0],
                            f'{min_lines}+ lines identical to {sorted(others)[0]}', 'D1/D2: reuse instead of copying'))
                i += min_lines
            else:
                i += 1
    return out


def main(argv):
    args = {'files': []}
    it = iter(argv)
    mode = None
    for a in it:
        if a in ('--staged', '--repo'):
            mode = a[2:]
        elif a in ('--diff', '--commit'):
            mode, args['ref'] = a[2:], next(it)
        elif a == '--files':
            mode = 'files'
        elif a in ('--config', '--root'):
            args[a[2:]] = next(it)
        elif a == '--json':
            args['json'] = True
        elif mode == 'files':
            args['files'].append(a)
        else:
            print(f'unknown argument {a}', file=sys.stderr)
            return 2
    if not mode:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        root = args.get('root') or git(os.getcwd(), 'rev-parse', '--show-toplevel').strip()
        cfg = load_config(args.get('config'))
    except (ValueError, OSError, json.JSONDecodeError, subprocess.CalledProcessError) as e:
        print(f'scan-code: configuration error: {e}', file=sys.stderr)
        return 2
    excl = [re.compile(x) for x in DEFAULT_EXCLUDE + cfg.get('exclude_paths', [])]
    excluded = lambda p: any(x.search(p) for x in excl)
    blocking, disabled = set(cfg.get('blocking', [])), set(cfg.get('disabled', []))
    allow = [(a['rule'], re.compile(a['path']), a['reason']) for a in cfg.get('allow', [])]
    safe_sql = [re.compile(x) for x in cfg.get('safe_sql_interpolations', [])]
    interp = re.compile(r'\$\{([^}]*)\}')
    def sql_is_parameterized(t):
        parts = interp.findall(t)
        return bool(parts) and bool(safe_sql) and all(any(x.match(pt.strip()) for x in safe_sql) for pt in parts)

    if mode == 'staged':
        lines = list(added_lines(git(root, 'diff', '--cached', '-U0', '--no-color', '--no-ext-diff')))
    elif mode == 'diff':
        lines = list(added_lines(git(root, 'diff', args['ref'], '-U0', '--no-color', '--no-ext-diff')))
    elif mode == 'commit':
        lines = list(added_lines(git(root, 'show', args['ref'], '--format=', '-U0', '--no-color', '--no-ext-diff')))
    elif mode == 'repo':
        lines = list(file_lines(root, git(root, 'ls-files').splitlines()))
    else:
        lines = list(file_lines(root, args['files']))
    lines = [(p, n, t) for p, n, t in lines if not excluded(p)]

    compiled = [(rid, name, re.compile(fr), re.compile(lr, re.I if rid in ('DC009', 'DC012') else 0),
                 re.compile(sp) if sp else None, re.compile(sl) if sl else None, why)
                for rid, name, fr, lr, sp, sl, why in RULES if rid not in disabled]
    findings = []
    for p, n, t in lines:
        for rid, name, fr, lr, sp, sl, why in compiled:
            if fr.search(p) and lr.search(t) and not (sp and sp.search(p)) and not (sl and sl.search(t)):
                if rid == 'DC010' and sql_is_parameterized(t):
                    continue
                findings.append([rid, name, p, n, t.strip()[:160], why])

    # DC008 is blocking only when the same variable is defaulted at more than one call site.
    if any(f[0] == 'DC008' for f in findings):
        sites = defaultdict(set)
        rx = re.compile(RULES[7][3])
        scan = lines if mode in ('repo', 'files') else list(file_lines(root, git(root, 'ls-files').splitlines()))
        for p, n, t in scan:
            if excluded(p) or re.search(TEST, p) or not re.search(CODE, p):
                continue
            for m in rx.finditer(t):
                sites[next(g for g in m.groups() if g and g not in ('||', '??'))].add((p, n))
        for f in findings:
            if f[0] == 'DC008':
                var = next((g for g in rx.search(f[4]).groups() if g and g not in ('||', '??')), None) if rx.search(f[4]) else None
                f.append(len(sites.get(var, ())) > 1)

    if 'DC013' not in disabled and mode != 'repo':
        findings += [list(x) for x in duplication(root, lines, int(cfg.get('thresholds', {}).get('dup_min_lines', 8)), excluded)]

    out = []
    for f in findings:
        rid, name, p, n, text, why = f[:6]
        repeated = f[6] if len(f) > 6 else None
        allowed = next((r for ar, ap, r in allow if ar == rid and ap.search(p)), None)
        block = rid in blocking and not allowed and (rid != 'DC008' or repeated)
        out.append({'rule': rid, 'name': name, 'path': p, 'line': n, 'text': text, 'why': why,
                    'level': 'allowed' if allowed else ('blocking' if block else 'advisory'),
                    **({'allowed_reason': allowed} if allowed else {}), **({'repeated': repeated} if repeated is not None else {})})
    nblock = sum(1 for o in out if o['level'] == 'blocking')
    if args.get('json'):
        print(json.dumps({'mode': mode, 'root': root, 'findings': out, 'blocking': nblock}, indent=1))
    else:
        for o in out:
            if o['level'] != 'allowed':
                print(f"{o['level'].upper():9} {o['rule']} {o['name']}  {o['path']}:{o['line']}  {o['text']}")
        if nblock:
            print(f'\nscan-code: {nblock} blocking finding(s). Fix them; a code comment does not waive a rule (D11).', file=sys.stderr)
    return 1 if nblock else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
