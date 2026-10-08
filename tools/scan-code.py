#!/usr/bin/env python3
"""
scan-code.py: deterministic code-quality checks for the shared Developer role.

Cheap, high-confidence mistakes are caught mechanically so review time goes to judgement. Every rule here is
ADVISORY unless the consuming organization's config lists it under "blocking", after measuring it against its
own repositories. A rule is never made blocking just because it exists.

Modes (exactly one):
  --staged              added lines in the git index (pre-commit)
  --diff BASE           added lines between BASE and the working tree
  --commit SHA          added lines of one commit, checked against that commit's tree (measurement)
  --patch FILE          added lines of a unified diff on disk (tests); no duplication check
  --repo                every line of every tracked file (measurement and audits)
  --files F [F ...]     every line of the named files

Options:
  --config FILE         organization config (JSON), below
  --root DIR            repository root (default: the current git top level)
  --json                machine-readable output

Config keys (all optional):
  blocking              rule ids that block (exit 1)
  disabled              rule ids that never run
  enabled               opt-in rule ids to run (an opt-in rule listed under blocking runs as well)
  allow                 [{rule, path, reason}]: a governed exception for one rule on matching paths; a reason
                        is required, and the config file is reviewed like code
  exclude_paths         extra path regexes never scanned; an entry may be {path, reason, ...}
  dup_exclude_paths     extra path regexes left out of the duplication check only (same form)
  code_extensions       extra code file extensions, without the dot
  config_paths          extra path regexes for configuration modules, where a default is legitimately defined
  config_read_patterns  extra regexes for the organization's own configuration reads that carry a literal
                        default; a named group (?P<var>...) lets repeated defaults be counted
  script_paths          extra path regexes for one-off scripts (host literals there are DC015, not DC014)
  host_allow            extra regexes for URLs and hosts the organization allows in code; an entry may be
                        {pattern, reason, ...}
  ticket_pattern        regex a TODO or FIXME must contain (DC016); default "#123" or "ABC-123"
  safe_sql_interpolations  regexes for interpolations the project's query builder parameterizes (DC010)
  thresholds            dup_min_lines (default 8): the shortest copied block reported;
                        dup_block_min_lines (default dup_min_lines): the shortest that is DC013 rather than DC022;
                        config_default_min_sites (default 2): call sites defaulting one variable before DC008
                        can block (1: any literal default can block)

Exit: 0 no blocking finding, 1 at least one blocking finding, 2 usage or configuration error.
A finding is suppressed only by the organization's config (rule + path + reason), never by a code comment:
a comment is not approval (D11).
"""
import hashlib, json, os, re, subprocess, sys
from collections import defaultdict

DEFAULT_EXCLUDE = [
    r'(^|/)node_modules/', r'(^|/)(dist|build|out|coverage|\.next|vendor|\.git)/', r'\.min\.(js|css)$',
    r'(^|/)(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|composer\.lock)$', r'\.(map|snap|svg|png|jpe?g|gif|ico|pdf|woff2?|ttf)$',
]
CODE_EXTS = ['ts', 'tsx', 'js', 'jsx', 'mjs', 'cjs', 'py', 'php', 'rb', 'go', 'java', 'cs', 'sh', 'bash']
CODE = r'\.(' + '|'.join(CODE_EXTS) + r')$'
JS = r'\.(ts|tsx|js|jsx|mjs|cjs)$'
TEST = r'(\.(test|spec)\.[a-z]+$|(^|/)(tests?|__tests__|__mocks__|spec|e2e|fixtures?)/|Test\.php$)'
DOC = r'\.(md|mdx|txt|rst)$'
SCRIPT_PATHS = [r'(^|/)(scripts?|bin|tools)/']
CONFIG_PATHS = [r'(^|/)(config|settings|conf)(/|$)', r'(^|/)[\w.-]*(config|settings|env)\.(ts|js|mjs|cjs|php|inc|py)$',
                r'(^|/)next\.config\.', r'(^|/)\.env']
# Copies here repeat legitimately (test setup, one-off scripts, per-environment configuration): DC022, never DC013.
RELAXED_PATHS = [r'(^|/)(scripts?|bin|tools|config|settings)/']
# URLs that name a schema, namespace, example or documentation link, not a host the program calls. An organization adds
# its own (well-known identity endpoints, for example) in host_allow.
DEFAULT_HOST_ALLOW = [
    r'(?:www\.)?(?:w3\.org|xmlns\.com|schemas\.(?:xmlsoap|microsoft|openxmlformats)\.(?:org|com)|json-schema\.org|purl\.org'
    r'|ns\.adobe\.com|schema\.org|example\.(?:com|org|net)|localhost|github\.com/[\w-]+/[\w.-]+/(?:commit|pull|issues)/)',
]
COMMENT_START = {  # language-aware comment markers
    'c': r'//|/\*', 'hash': r'#(?![!\[{])', 'sql': r'--\s', 'cfml': r'<!---',
}
LANG_COMMENTS = [
    (r'\.(ts|tsx|js|jsx|mjs|cjs|java|cs|go)$', ['c']),
    (r'\.(php|inc)$', ['c', 'hash']),
    (r'\.(py|rb|sh|bash)$', ['hash']),
    (r'\.sql$', ['sql', 'c']),
    (r'\.(cfc|cfm)$', ['cfml', 'c']),
]
COMMENT_LINE = re.compile(r'^\s*(//|#(?!!)|\*|/\*|--|<!--)')

# Rules: id, name, file regex, line regex, skip-path regex, skip-line regex, why, target (code | comment | line),
# opt-in. Code rules see the line without its trailing comment; comment rules see only the comment.
RULES = [
    ('DC001', 'tls-verification-disabled', CODE,
     r'rejectUnauthorized\s*:\s*false|NODE_TLS_REJECT_UNAUTHORIZED\s*=\s*[\'"]?0|\bverify\s*=\s*False\b|CURLOPT_SSL_VERIFY(PEER|HOST)\s*(,|=>)\s*(false|0)\b|InsecureSkipVerify\s*:\s*true|\bcurl\b[^\n]*\s(-k|--insecure)\b',
     None, None, 'D5: TLS verification stays enabled', 'code', False),
    ('DC002', 'dynamic-code-execution', CODE,
     r'(?<![\w.$])eval\s*\(|\bnew\s+Function\s*\(|\bvm\.(runIn\w+|Script)\b|(?<![\w.])exec\s*\(\s*(?![\'"])|\bcreate_function\s*\(|\bextract\s*\(\s*\$',
     None, r'^\s*(//|#|\*)', 'D5: never dynamically execute untrusted input', 'code', False),
    ('DC003', 'unsafe-deserialization', CODE,
     r'\bpickle\.loads?\s*\(|\byaml\.load\s*\((?![^)]*SafeLoader)|(?<![\w>])unserialize\s*\(|\bmarshal\.loads?\s*\(|node-serialize|\bObjectInputStream\b',
     None, r'^\s*(//|#|\*)', 'D5: never use unsafe deserialization', 'code', False),
    ('DC004', 'debug-artifact', CODE,
     r'^\s*debugger\s*;?\s*$|\bvar_dump\s*\(|\bprint_r\s*\((?!(?:[^()]|\([^()]*\))*,\s*true\s*\))|(?<![\w.>$:])dd\s*\(|\bpdb\.set_trace\s*\(|(?<![\w.])breakpoint\s*\(\s*\)',
     TEST, r'^\s*(//|#|\*)|\bfunction\s+dd\s*\(', 'Debug artefacts are removed before commit', 'code', False),
    ('DC005', 'console-log', JS, r'\bconsole\.(log|debug)\s*\(', TEST + r'|(^|/)(scripts?|tools?|bin)/', r'^\s*(//|\*)',
     'Debug output in application code', 'code', False),
    ('DC006', 'localhost-endpoint', CODE, r'https?://(localhost|127\.0\.0\.1|0\.0\.0\.0)(:\d+)?\b',
     TEST + r'|(^|/)(scripts?|tools?|bin|docs?)/|(^|/)[^/]*\.config\.[a-z]+$', r'^\s*(//|#|\*)',
     'D3: runtime endpoints come from configuration', 'code', False),
    ('DC007', 'private-network-literal', CODE, r'\b(10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b',
     TEST, r'^\s*(//|#|\*)', 'D3: hosts come from configuration', 'code', False),
    # DC008 is matched by config_default() below; this row carries its metadata.
    ('DC008', 'config-default-at-call-site', CODE, None,
     TEST, r'^\s*(//|#|\*)', 'D3: a default is defined once, not repeated at call sites', 'code', False),
    ('DC009', 'money-as-float', CODE,
     r'parseFloat\([^)]*(price|amount|total|cost|fee|balance)|\b(price|amount|total|cost|fee|balance)\w*\s*[*/]\s*\d+\.\d+|\.toFixed\(\s*2\s*\)'
     r'|(\(float\)|floatval\(|\bfloat\(|Number\()\s*[^;]{0,60}(price|amount|total|cost|revenue|balance|fee|tax|invoice)',
     TEST, r'^\s*(//|#|\*)', 'D6: money uses integer minor units or fixed-precision decimal', 'code', False),
    ('DC010', 'sql-string-building', CODE,
     r'`[^`]*\b(SELECT|INSERT\s+INTO|UPDATE|DELETE\s+FROM)\b[^`]*\$\{|[\'"]\s*(SELECT|INSERT\s+INTO|UPDATE|DELETE\s+FROM)\b[^\'"]*[\'"]\s*(\+|\.)\s*\$?\w',
     TEST, r'^\s*(//|#|\*)', 'D5: parameterize queries', 'code', False),
    ('DC011', 'numeric-id-literal', CODE, r'[!=]==?\s*(?!(19|20)\d\d\b)\d{4,}\b|\b(?!(19|20)\d\d\b)\d{4,}\s*[!=]==?',
     TEST, r'^\s*(//|#|\*)', 'D3: identifiers come from configuration or data', 'code', False),
    ('DC012', 'waiver-comment', CODE,
     r'(TODO|FIXME|HACK|XXX)\b[^\n]*(hard.?cod|temporar|for now|bypass|skip (the )?check)|eslint-disable(?:-next-line)?\s*$|@ts-(ignore|nocheck)\s*$',
     TEST, None, 'D11: a comment acknowledging a violation is not approval', 'line', False),
    # Opt-in rules: off unless the organization's config lists them under "enabled" or "blocking".
    ('DC014', 'host-literal', CODE, None, TEST, None, 'D3: URLs, IP addresses and host names come from configuration', 'code', True),
    ('DC015', 'host-literal-script-or-markup', CODE, None, TEST, None,
     'D3: a host in a one-off script or a markup link; read it from configuration if the code calls it', 'code', True),
    ('DC016', 'todo-without-ticket', CODE, r'\b(?:TODO|FIXME|XXX)\b', None, None,
     'A TODO or FIXME names its ticket, or it is never done', 'comment', True),
    ('DC017', 'deviation-comment', CODE, None, None, None,
     'D11: a comment that records a copy or an exception is not approval; raise the departure', 'comment', True),
    ('DC018', 'deviation-wording', CODE, None, None, None,
     'D11: the comment suggests a deviation; if it departs from a Hard rule, raise it', 'comment', True),
    ('DC019', 'config-empty-default', CODE, None, TEST, None,
     'D3: an empty default at a configuration read; if the value is required, fail loudly instead', 'code', True),
    ('DC020', 'unexplained-numeric-literal', CODE, r'(?<![\w.$\'"#-])\d{3,}(?![\w.\'"])', TEST, None,
     'D3: a numeric literal of three or more digits with no comment; name it or read it from configuration', 'code', True),
    ('DC021', 'cfml-evaluate', r'\.(cfc|cfm)$', r'(?i)\bevaluate\s*\(', None, None,
     'D5: CFML Evaluate executes a string; use structure or bracket access', 'code', True),
]
DUP_RULES = [('DC013', 'possible-duplication', False), ('DC022', 'possible-duplication-short', True)]
OPT_IN = {r[0] for r in RULES if r[8]} | {d[0] for d in DUP_RULES if d[2]}
ALL_IDS = [r[0] for r in RULES] + [d[0] for d in DUP_RULES]
META = {r[0]: (r[1], r[6]) for r in RULES}
META.update({'DC013': ('possible-duplication', 'D1/D2: reuse instead of copying'),
             'DC022': ('possible-duplication-short', 'D1/D2: a short or relaxed-path copy; reuse it if the copy is real')})

CONFIG_READS = [
    r'process\.env\.(?P<var>\w+)\s*(?:\|\||\?\?)\s*(?P<def>[\'"`\d\[{])',
    r'os\.(?:environ\.get|getenv)\(\s*[\'"](?P<var>[^\'"]+)[\'"]\s*,\s*(?P<def>[\'"\d\[{])',
    r'getenv\(\s*[\'"]?(?P<var>[^\'")]*)[\'"]?\s*\)\s*\?:\s*(?!throw\b)(?P<def>\S)',
    r'\$_ENV\[\s*[\'"]?(?P<var>[^\'"\]]+)[\'"]?\s*\]\s*\?\?\s*(?!\$|throw\b)(?P<def>\S)',
    r'\$GLOBALS\[\s*[\'"]?(?P<var>[^\'"\]]+)[\'"]?\s*\]\s*\?\?(?!=)\s*(?!\$|throw\b)(?P<def>\S)',
]
EMPTY_DEFAULT = re.compile(r'(?:,\s*|\?\?\s*|\?:\s*|\|\|\s*)(?:\'\'|""|``|\[\]|null|None|undefined)\s*(?:[),;]|$)')
HOST_LITERAL = re.compile(
    r'[\'"`](?:https?|wss?|s?ftp|postgres(?:ql)?|mysql|mssql|sqlserver|redis|amqps?|ldaps?|mongodb(?:\+srv)?|smtps?)://[^\'"`\s]+'
    r'|[\'"`](?!0\.0\.0\.0|127\.0\.0\.1)(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?[\'"`/]'
    r'|[\'"`][\w-]+(?:\.[\w-]+)+\.(?:ca|com|net|org|io|internal|local|corp)(?::\d+)?[\'"`/]')
TEMPLATED_HOST = re.compile(r'://(?:\$\{|\{\$|\$\w|\{|\'\s*\+|"\s*\+|`\s*\+)')
XMLNS = re.compile(r'xmlns(?::\w+)?\s*=|[\'"]?\b(?:uri|namespace|targetNamespace)\b[\'"]?\s*(?:=>|=|:)', re.I)
MARKUP_LINK = re.compile(r'\b(?:href|src|action|srcset|poster)\s*=\s*[\'"]https?://', re.I)
# A comment that points at code it copied, or that ties two pieces of code together, records a deviation.
CODE_REF = r'(?:\S*\w\(\)|\S+\.(?:php|inc|ts|tsx|js|jsx|py|sql|cfc|cfm|sh|rb|go|java|cs)\b|\S*::\w+|\S+/\S+)'
DEVIATION_STRONG = re.compile(
    r'second copy|duplicate(?:d)? (?:of|from) .{0,30}?' + CODE_REF + r'|keep (?:this |these |it |them )?in sync with .{0,30}?' + CODE_REF
    + r'|if .{1,80} changes?,? (?:you must |also |then )?(?:also )?change\b', re.I)
DEVIATION_NEGATED = re.compile(r'instead of|rather than|\bavoids?\b|\bnever\b|\bno longer\b|\bwithout\b|\bnot\b', re.I)
DEVIATION_BROAD = re.compile(r'copied (?:from|verbatim)|duplicate(?:d)? (?:of|from)|keep (?:this |these |it |them )?in sync|\bhack\b'
                             r'|workaround|\bfor now\b|\btemporar(?:y|ily)\b|quick fix|same as .{0,60}\bin\b', re.I)
CONST_DECL = re.compile(r'\b(?:const|define\s*\(|final\s+const|private\s+const|public\s+const|protected\s+const)\b|^\s*[A-Z][A-Z0-9_]+\s*=')
DEFAULT_TICKET = r'#\d+|\b[A-Z][A-Z0-9]+-\d+'


# Duplication: lines that carry no logic are dropped before blocks are compared.
DUP_TRIVIAL = re.compile(r'^[\s{}()\[\];,.:<>/"\'`]*$|^(end|else|try|finally|return;?|break;?|continue;?|\?>|<\?php|default:)$'
                         r'|^(use|namespace|import|from|require|require_once|include|include_once|export \* from|export \{)\b'
                         r'|^</?[a-z][\w.-]*\s*/?>$')
DUP_COMMENT = re.compile(r'^\s*(//|#(?!!)|\*|/\*|\*/|--|<!--)')

GIT_TIMEOUT_S = 120


def git(root, *args, check=True):
    return subprocess.run(['git', '-C', root, *args], capture_output=True, text=True, errors='replace',
                          check=check, timeout=GIT_TIMEOUT_S).stdout


def load_config(path):
    if not path:
        return {}
    with open(path) as f:
        cfg = json.load(f)
    for rid in cfg.get('blocking', []) + cfg.get('disabled', []) + cfg.get('enabled', []):
        if rid not in ALL_IDS:
            raise ValueError(f'unknown rule id in config: {rid}')
    for a in cfg.get('allow', []):
        if not a.get('reason'):
            raise ValueError(f'allow entry without a reason: {a}')
    # An exclusion may carry its reason: {"path": regex, "reason": ...}; a bare regex is a plain exclusion.
    for key, field in (('exclude_paths', 'path'), ('dup_exclude_paths', 'path'), ('host_allow', 'pattern')):
        out = []
        for x in cfg.get(key, []):
            if isinstance(x, dict):
                if not x.get(field) or not x.get('reason'):
                    raise ValueError(f'{key} entry needs a {field} and a reason: {x}')
                x = x[field]
            out.append(x)
        cfg[key] = out
    for key in ('exclude_paths', 'dup_exclude_paths', 'config_paths', 'config_read_patterns', 'script_paths',
                'host_allow', 'safe_sql_interpolations'):
        for x in cfg.get(key, []):
            re.compile(x)
    if cfg.get('ticket_pattern'):
        re.compile(cfg['ticket_pattern'])
    th = cfg.get('thresholds', {})
    for k in ('dup_min_lines', 'dup_block_min_lines', 'config_default_min_sites'):
        if k in th and (not isinstance(th[k], int) or th[k] < 1):
            raise ValueError(f'thresholds.{k} must be a positive integer')
    return cfg


def added_lines(diff_text):
    """Yield (path, line_no, text) for every added line in a unified diff."""
    path, line = None, 0
    # Split on newlines only: str.splitlines() also breaks on form feeds and Unicode separators inside a line,
    # which shifts every later line number.
    for raw in diff_text.split('\n'):
        if raw.startswith('+++ '):
            p = raw[4:].strip()
            path = None if p == '/dev/null' else re.sub(r'^b/', '', p)
        elif raw.startswith('@@'):
            m = re.search(r'\+(\d+)', raw)
            line = int(m.group(1)) if m else 0
        elif path and raw.startswith('+') and not raw.startswith('+++'):
            yield path, line, raw[1:]
            line += 1
        elif path and not raw.startswith('-') and not raw.startswith('\\'):
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


def split_comment(path, text):
    """(code, comment): the line without a trailing comment, and the comment, by the file's language."""
    if COMMENT_LINE.match(text):
        return '', text
    kinds = next((k for rx, k in LANG_COMMENTS if re.search(rx, path)), ['c', 'hash'])
    start = re.compile('|'.join(COMMENT_START[k] for k in kinds))
    in_str = None
    for i, ch in enumerate(text):
        if in_str:
            if ch == in_str and text[i - 1] != '\\':
                in_str = None
            continue
        if ch in '\'"`':
            in_str = ch
            continue
        if start.match(text, i):
            return text[:i], text[i:]
    return text, ''


def config_default(code, extra):
    """(variable or None, empty-default?) for a configuration read that carries a literal default."""
    for rx in CONFIG_READS + extra:
        m = re.search(rx, code)
        if m:
            var = m.groupdict().get('var')
            return (var.strip() if var else None), bool(EMPTY_DEFAULT.search(code[m.start():]))
    return None


# Duplication -------------------------------------------------------------------------------------------------

def dup_normalize(line):
    if DUP_COMMENT.match(line):
        return None
    s = re.sub(r'\s+', ' ', line.strip().lower())
    return None if not s or DUP_TRIVIAL.match(s) else s


def windows(lines, size):
    """[(hash, first_line, last_line)] for every run of `size` meaningful lines."""
    meaningful = [(i + 1, s) for i, s in enumerate(dup_normalize(l) for l in lines) if s]
    return [(hashlib.sha1('\n'.join(s for _, s in meaningful[i:i + size]).encode()).hexdigest(),
             meaningful[i][0], meaningful[i + size - 1][0]) for i in range(len(meaningful) - size + 1)]


def read_blobs(root, shas):
    """Contents of many blobs in one git process."""
    if not shas:
        return {}
    proc = subprocess.run(['git', '-C', root, 'cat-file', '--batch'], input=('\n'.join(shas) + '\n').encode(),
                          capture_output=True, timeout=GIT_TIMEOUT_S)
    out, data, pos = {}, proc.stdout, 0
    while pos < len(data):
        nl = data.index(b'\n', pos)
        header = data[pos:nl].split()
        pos = nl + 1
        if len(header) < 3 or header[1] == b'missing':
            continue
        size = int(header[2])
        out[header[0].decode()] = data[pos:pos + size].decode('utf-8', 'replace')
        pos += size + 1
    return out


def tree_texts(root, mode, ref):
    """{path: text} of the tree the change is compared with: the index, the commit, or the working tree."""
    if mode == 'staged':
        entries = [(l.split('\t')[1], l.split('\t')[0].split()[1]) for l in git(root, 'ls-files', '-s').splitlines() if '\t' in l]
    elif mode == 'commit':
        entries = [(l.split('\t')[1], l.split('\t')[0].split()[2]) for l in git(root, 'ls-tree', '-r', ref).splitlines()
                   if '\t' in l and l.split()[1] == 'blob']
    else:
        return None
    return entries


def duplication(root, mode, ref, adds, cfg, excluded, code_rx, enabled):
    """Added blocks that repeat code elsewhere in the tree (or elsewhere in the same change)."""
    th = cfg.get('thresholds', {})
    min_lines = th.get('dup_min_lines', 8)
    block_min = th.get('dup_block_min_lines', min_lines)
    short_on = 'DC022' in enabled
    size = min(min_lines, block_min) if short_on else block_min
    dex = [re.compile(x) for x in cfg.get('dup_exclude_paths', [])]
    relaxed = [re.compile(x) for x in RELAXED_PATHS]
    test_rx = re.compile(TEST)
    skip = lambda p: excluded(p) or any(x.search(p) for x in dex)
    added = defaultdict(set)
    for p, n, _ in adds:
        if code_rx.search(p) and not skip(p):
            added[p].add(n)
    if not added:
        return []
    exts = {os.path.splitext(p)[1] for p in added}
    entries = tree_texts(root, mode, ref)
    if entries is None:
        paths = [p for p in git(root, 'ls-files').splitlines()] + [p for p in added]
        texts = {}
        for p in set(paths):
            if os.path.splitext(p)[1] in exts and not skip(p):
                try:
                    with open(os.path.join(root, p), encoding='utf-8', errors='replace') as f:
                        texts[p] = f.read()
                except (IsADirectoryError, FileNotFoundError):
                    pass
    else:
        entries = [(p, s) for p, s in entries if os.path.splitext(p)[1] in exts and not skip(p)]
        blobs = read_blobs(root, [s for _, s in entries])
        texts = {p: blobs.get(s, '') for p, s in entries}
    index = defaultdict(list)
    for p, text in texts.items():
        for h, a, b in windows(text.split('\n'), size):
            index[h].append((p, a, b))
    raw = []
    for p, new in added.items():
        lines = texts.get(p, '').split('\n')
        for h, a, b in windows(lines, size):
            if not any(n in new for n in range(a, b + 1)):
                continue
            others = [(q, x, y) for q, x, y in index.get(h, []) if not (q == p and x == a)]
            if others:
                raw.append((p, a, b) + others[0])
    merged, last = [], None
    for f in sorted(raw):
        if last and f[0] == last[0] and f[1] <= last[2] + 1 and f[3] == last[3]:
            last = (last[0], last[1], max(last[2], f[2]), last[3], last[4], max(last[5], f[5]))
            merged[-1] = last
            continue
        merged.append(f)
        last = f
    out = []
    for p, a, b, q, x, y in merged:
        lines = texts.get(p, '').split('\n')
        length = sum(1 for n in range(a, b + 1) if n - 1 < len(lines) and dup_normalize(lines[n - 1]) and n in added[p])
        relaxed_path = bool(test_rx.search(p)) or any(r.search(p) for r in relaxed)
        if short_on and (relaxed_path or length < block_min):
            rid = 'DC022'
        elif not short_on and test_rx.search(p):
            continue
        else:
            rid = 'DC013' if length >= block_min else None
        if rid:
            out.append([rid, META[rid][0], p, a, f'{length} added lines repeat {q}:{x}-{y}', META[rid][1]])
    return out


# Main --------------------------------------------------------------------------------------------------------

def main(argv):
    args = {'files': []}
    it = iter(argv)
    mode = None
    for a in it:
        if a in ('--staged', '--repo'):
            mode = a[2:]
        elif a in ('--diff', '--commit', '--patch'):
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
    except (ValueError, OSError, re.error, json.JSONDecodeError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        print(f'scan-code: configuration error: {e}', file=sys.stderr)
        return 2
    excl = [re.compile(x) for x in DEFAULT_EXCLUDE + cfg.get('exclude_paths', [])]
    excluded = lambda p: any(x.search(p) for x in excl)
    blocking, disabled = set(cfg.get('blocking', [])), set(cfg.get('disabled', []))
    enabled = (set(cfg.get('enabled', [])) | (blocking & OPT_IN)) - disabled
    active = lambda rid: rid not in disabled and (rid not in OPT_IN or rid in enabled)
    allow = [(a['rule'], re.compile(a['path']), a['reason']) for a in cfg.get('allow', [])]
    safe_sql = [re.compile(x) for x in cfg.get('safe_sql_interpolations', [])]
    code_rx = re.compile(r'\.(' + '|'.join(CODE_EXTS + list(cfg.get('code_extensions', []))) + r')$')
    config_rx = [re.compile(x) for x in CONFIG_PATHS + cfg.get('config_paths', [])]
    script_rx = [re.compile(x) for x in SCRIPT_PATHS + cfg.get('script_paths', [])]
    host_allow = [re.compile(x, re.I) for x in DEFAULT_HOST_ALLOW + cfg.get('host_allow', [])]
    ticket = re.compile(cfg.get('ticket_pattern') or DEFAULT_TICKET)
    extra_reads = cfg.get('config_read_patterns', [])
    min_sites = cfg.get('thresholds', {}).get('config_default_min_sites', 2)
    interp = re.compile(r'\$\{([^}]*)\}')

    def sql_is_parameterized(t):
        parts = interp.findall(t)
        return bool(parts) and bool(safe_sql) and all(any(x.match(pt.strip()) for x in safe_sql) for pt in parts)

    try:
        if mode == 'staged':
            lines = list(added_lines(git(root, 'diff', '--cached', '-U0', '--no-color', '--no-ext-diff')))
        elif mode == 'diff':
            lines = list(added_lines(git(root, 'diff', args['ref'], '-U0', '--no-color', '--no-ext-diff')))
        elif mode == 'commit':
            lines = list(added_lines(git(root, 'show', args['ref'], '--format=', '-U0', '--no-color', '--no-ext-diff', '--first-parent')))
        elif mode == 'patch':
            with open(args['ref'], encoding='utf-8', errors='replace') as f:
                lines = list(added_lines(f.read()))
        elif mode == 'repo':
            lines = list(file_lines(root, git(root, 'ls-files').splitlines()))
        else:
            lines = list(file_lines(root, args['files']))
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        print(f'scan-code: cannot read the change: {e}', file=sys.stderr)
        return 2
    lines = [(p, n, t) for p, n, t in lines if not excluded(p)]

    compiled = []
    for rid, name, fr, lr, sp, sl, why, target, _ in RULES:
        if not active(rid):
            continue
        frx = code_rx if fr == CODE else re.compile(fr)
        compiled.append((rid, name, frx, re.compile(lr, re.I if rid in ('DC009', 'DC012') else 0) if lr else None,
                         re.compile(sp) if sp else None, re.compile(sl) if sl else None, why, target))
    findings = []
    for p, n, t in lines:
        code, comment = split_comment(p, t)
        is_config = any(x.search(p) for x in config_rx)
        is_script = any(x.search(p) for x in script_rx)
        for rid, name, fr, lr, sp, sl, why, target in compiled:
            if not fr.search(p) or (sp and sp.search(p)) or (sl and sl.search(t)):
                continue
            subject = {'code': code, 'comment': comment, 'line': t}[target]
            if not subject:
                continue
            hit = False
            if rid in ('DC008', 'DC019'):
                cd = None if is_config else config_default(code, extra_reads)
                if not cd:
                    continue
                var, empty = cd
                if rid == 'DC008':
                    if not (empty and active('DC019')):
                        findings.append([rid, name, p, n, t.strip()[:160], why, var])
                    continue
                hit = empty
            elif rid in ('DC014', 'DC015'):
                urls = HOST_LITERAL.findall(code)
                if is_config or not urls or XMLNS.search(code):
                    continue
                if all(any(h.search(u) for h in host_allow) or TEMPLATED_HOST.search(u) for u in urls):
                    continue
                soft = is_script or bool(MARKUP_LINK.search(code))
                hit = soft if rid == 'DC015' else not soft
            elif rid == 'DC016':
                m = lr.search(comment)
                hit = bool(m) and not ticket.search(comment[m.start():])
            elif rid == 'DC017':
                hit = bool(DEVIATION_STRONG.search(comment)) and not DEVIATION_NEGATED.search(comment)
            elif rid == 'DC018':
                strong = DEVIATION_STRONG.search(comment) and not DEVIATION_NEGATED.search(comment)
                hit = not strong and bool(DEVIATION_STRONG.search(comment) or DEVIATION_BROAD.search(comment))
            elif rid == 'DC020':
                hit = not comment.strip() and not CONST_DECL.search(code) and bool(lr.search(code))
            else:
                hit = bool(lr.search(subject))
                if hit and rid == 'DC010' and sql_is_parameterized(t):
                    hit = False
            if hit:
                findings.append([rid, name, p, n, t.strip()[:160], why])

    # DC008 blocks only when at least config_default_min_sites call sites default the same variable.
    if any(f[0] == 'DC008' for f in findings):
        if min_sites <= 1:
            for f in findings:
                if f[0] == 'DC008':
                    f[6] = True
        else:
            sites = defaultdict(set)
            scan = lines if mode in ('repo', 'files') else list(file_lines(root, git(root, 'ls-files').splitlines()))
            for p, n, t in scan:
                if excluded(p) or re.search(TEST, p) or not code_rx.search(p) or any(x.search(p) for x in config_rx):
                    continue
                cd = config_default(split_comment(p, t)[0], extra_reads)
                if cd and cd[0]:
                    sites[cd[0]].add((p, n))
            for f in findings:
                if f[0] == 'DC008':
                    f[6] = bool(f[6]) and len(sites.get(f[6], ())) >= min_sites

    if active('DC013') and mode not in ('repo', 'patch'):
        try:
            findings += duplication(root, mode, args.get('ref'), lines, cfg, excluded, code_rx, enabled)
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            print(f'scan-code: duplication check failed: {e}', file=sys.stderr)
            return 2

    out = []
    for f in findings:
        rid, name, p, n, text, why = f[:6]
        repeated = f[6] if len(f) > 6 else None
        allowed = next((r for ar, ap, r in allow if ar == rid and ap.search(p)), None)
        block = rid in blocking and not allowed and (rid != 'DC008' or repeated)
        out.append({'rule': rid, 'name': name, 'path': p, 'line': n, 'text': text, 'why': why,
                    'level': 'allowed' if allowed else ('blocking' if block else 'advisory'),
                    **({'allowed_reason': allowed} if allowed else {}), **({'repeated': bool(repeated)} if rid == 'DC008' else {})})
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
