# Development Standards

The patterns behind D1 to D15 (`DEVELOPER_RULES.md`): what "written right the first time" looks like, in any
stack. The organization or project adds its own conventions (naming, frameworks, components) in its own
layer. Where a pattern here is a heuristic it is a guideline under the Hard and Guideline semantics.

---

## Purpose and mental model

The intent of this document is to make the code-review gate **find nothing**. A code review that fixes ten things means the code wasn't written right the first time. A code review that catches a typo and a minor style issue means the development standards held.

That goal is aspirational, not literal — review always catches something. But the framing matters: development standards are the *primary* quality gate; review is the *backstop*. Pushing quality "left" (earlier in the lifecycle) is consistently the highest-leverage move a team can make. Bugs caught at code-time cost ~1x. Bugs caught at review cost ~10x. Bugs caught in production cost ~100x and beyond.

This document codifies the patterns and disciplines that put us as close to "right the first time" as is realistic, organized so the patterns are reachable in seconds.

---

## Stack-agnostic core principles

These five principles compound. Internalizing them is the most important thing in this document.

### YAGNI — You Aren't Gonna Need It

Build for the requirement, not the speculation. If you add an abstraction layer "in case we need it later," you have just guaranteed two costs (build + maintain) for a future benefit that may never arrive. Concrete code that works today beats abstract code that might work tomorrow.

**Test:** before adding a parameter, an option, a config knob, or an interface — ask "is there a current caller that needs this?" If no, do not add it.

### SOLID

The most-used of the SOLID principles in real codebases:

- **S** — Single Responsibility. One class, one reason to change. If you can't describe a class in one sentence without "and" or "also," it's too big.
- **O** — Open/Closed. Open to extension, closed to modification. Add new capability via new classes/strategies; do not edit existing tested classes for new features.
- **L** — Liskov Substitution. If `Foo` extends `Bar`, anywhere `Bar` is used, `Foo` must work without surprises. Subclasses must honour the contract of the parent.
- **I** — Interface Segregation. Many small interfaces over one fat interface. Callers shouldn't depend on methods they don't use.
- **D** — Dependency Inversion. Depend on abstractions, not concretions. Pass the dependency in (constructor / function parameter), don't reach out to a global.

### DRY — Don't Repeat Yourself (but beware premature abstraction)

If you write the same logic in three places, extract it. Two places — judgement call; if the two will diverge naturally, leave them. Premature abstraction is worse than duplication because abstractions are expensive to undo once callers rely on them. The rule of thumb: write it the second time, extract it the third time.

### KISS — Keep It Simple

Code is read ten times more often than written. Optimise for the reader, not the writer. The line you understand in two seconds beats the line you need to puzzle out for two minutes, even if the second is "more elegant." Clever code is a tax on every future reader, including yourself in six months.

### Fail Fast

When something is wrong, error out at the earliest possible point with the clearest possible message. Silent fallbacks and best-effort handling are the most expensive bugs in software. A production identifier used in development because an environment variable was not set is the classic example: fail fast and the bug surfaces on day one; silently default and it surfaces months later as an incident.

---

## Pre-coding checklist

Run before writing the first line of code on any change beyond a one-line tweak:

- [ ] **Read the existing code.** What's already there for this concern? Don't add a third customer lookup when two already exist (D1).
- [ ] **Identify all files that will change.** Surface the full scope before you start. Discovering at hour 4 that this also touches three other files is a planning failure.
- [ ] **Search for reusable helpers.** Grep for the verb you're about to write (`fetchAccount`, `parseDate`, `validateEmail`). If it exists, use it. If close-but-not-quite exists, generalize it. Only write new if nothing matches.
- [ ] **Decide the public interface first.** Method signatures, return shapes, error shapes — design these before the body. This is the contract; the body is the implementation detail.
- [ ] **Plan the failure modes.** What happens on null input? Empty input? Network failure? Downstream 5xx? Timeout? Decide before coding, not during.
- [ ] **Plan the tests alongside.** What scenarios will the test suite cover? Listing them now prevents "I'll add tests later" debt.
- [ ] **Decide the review depth.** Low, Normal or High by the surfaces touched (`REVIEW_METHOD.md`); the organization's release tier governs release handling separately.

A change that skips this checklist is a change that will need rework.

---

## Patterns to follow

### Configuration and secrets

| Pattern | Why |
|---|---|
| Read every configurable value from the authoritative config source, defined once (D3) | Behaviour changes per environment without code changes, and a default is never repeated at call sites |
| Fail loudly with a typed `ConfigError` if a required value is missing | Silent fallback is the most expensive bug class (D3) |
| Document each new config key with WHAT it controls and WHY this default | Future readers can audit and tune |
| Secrets never in code, never in logs | D5, D7 |
| Encryption keys never in the same location as the encrypted data | Key and data compromised together otherwise |
| Default to the safest value | When in doubt, the default should fail closed, not open |
| Never execute code a user, a model, or stored data supplied | `eval`, `new Function`, `vm`, shell: a user-script feature is a remote-code-execution hole (D5) |
| Never fetch a URL a caller chose from the server | Server-side request forgery reaches internal services and cloud metadata (D5) |

### Error handling

| Pattern | Why |
|---|---|
| Typed exception hierarchy (`ConfigError`, `NetworkError`, `MappingError`, etc.) | Retry semantics, alerting, logging all depend on knowing the error class |
| Every `catch` either handles, transforms, or rethrows | "Catch and pass" is the most expensive code smell in the codebase |
| Resource cleanup via `try/finally` or RAII | Leaked DB handles / file handles / connections compound under load |
| Errors carry context, not just messages | `"Database error"` is useless; `"Could not connect to billing DB at host X (timeout after 5s, run_uuid=abc-123)"` is debuggable |
| User-facing errors never leak internals | Stack traces, DB errors, config keys stay server-side |
| Retries have a budget | Exponential backoff with a cap; never infinite retry |
| Critical paths have an "alert on failure" branch | And the alert itself never aborts the critical path |
| Time budgets on long-running operations | Hard timeout before the OS or cron kills the process mid-write |

### Logging and observability

| Pattern | Why |
|---|---|
| Structured logs (JSON / JSONL where downstream consumes) | Searchable, filterable, machine-friendly |
| Correlation IDs threaded through every log line | One operation traceable end-to-end |
| Log levels intentional: DEBUG / INFO / WARN / ERROR / CRITICAL | Operators read by level; misclassified levels create noise |
| PII redacted at the log boundary | Single source of truth for redaction patterns; tested |
| Bounded log payloads (size cap + depth cap) | Unbounded logging is a disk-fill outage waiting to happen |
| Metrics emitted for key counters | Operations need numbers, not just words |

### Naming

| Pattern | Why |
|---|---|
| Names express intent, not type | `customers` over `customerArray`; `totalRevenue` over `intResult` |
| Booleans named so the value's meaning is unambiguous | `isReady`, `hasItems`, `shouldRetry` — not `flag`, `ready`, or `done` |
| Functions are verbs; classes are nouns; constants UPPERCASE | Cross-language convention |
| No undefined abbreviations | `cust`, `addr`, `qty` are universal; `xfm`, `cnsq`, `wkfl` are not |
| Same concept, same name, across the codebase | `customer` and `client` and `account` should not coexist meaning the same thing |
| Names that read aloud in plain English | `if (user.canAccess(resource))` reads; `if (cAcc(u, r))` does not |

### Function / method design

| Pattern | Why |
|---|---|
| One function = one thing | If you can't name it in 5 words without "and," split it |
| Body fits on screen | Soft cap ~50 LOC; hard cap ~100 LOC (guideline) |
| 4 or fewer positional parameters | Beyond that, pass an options object / DTO (guideline) |
| Pure where possible | Pure functions are infinitely easier to test |
| Side effects isolated to the edges | The "functional core, imperative shell" pattern |
| Default values for optional parameters | Optional parameters trail required ones |
| Early return for guard clauses | Reduces nesting; the happy path stays at the leftmost indent |

### Class design

| Pattern | Why |
|---|---|
| One class per file | Findability; one place to look |
| `final` by default; remove only if subclassing is intentional | Prevents surprising extension; signals design intent |
| Composition over inheritance | Inheritance creates tight coupling; composition is reusable |
| Interfaces define contracts; abstract classes share implementation | Decouple "what" from "how" |
| Constructor does no work | Construction should not fail; failure happens in named methods with clear semantics |
| Immutability by default | If a field can be set once, make it readonly |

### Reusability

| Pattern | Why |
|---|---|
| Reuse what exists before writing (D1) | Single-use copies are the source of duplication |
| No speculative abstraction for hypothetical callers (D13) | An abstraction with no second caller is cost without benefit |
| Extract on the third use, not the second | The shape of the abstraction is clear by the third caller |
| Promote to shared module when used across modules | Stays in the right scope as it grows |
| Deployment-specific values are configuration, invariant domain constants may stay in code (D3) | A magic number that varies by environment is a config key |
| One authoritative definition per business rule (D2) | Reuse it where technically appropriate; across a system boundary consume its result. Necessary replication is explicit, justified, tested against the authority and approved when material |

### Data layer

| Pattern | Why |
|---|---|
| Parameterized queries always; string concatenation never | SQL injection is a one-mistake breach |
| Indexes for FK columns and frequent query shapes | Without indexes, queries scale O(n); with, O(log n) |
| Soft delete where the project convention uses it (`is_deleted = true`), with a real deletion path where law requires erasure | Audit trail and reversibility, without blocking erasure obligations |
| Standard columns on every table, as the project convention defines them | Consistency wins |
| UUIDs in public-facing IDs; never numeric primary keys | Prevents IDOR enumeration |
| Migrations idempotent and reversible | Production deploys need an out |
| `SELECT *` never in app code; always list columns | Future schema additions don't surprise the app |

### Environments and configuration defaults

| Pattern | Why |
|---|---|
| Code that joins two systems verifies their environment identities are compatible before it reads or writes, and fails closed when it cannot | A development database paired with a production system writes test values into live records (D4) |
| Each default is defined once, in the configuration source; call sites read the value and fail loudly if it is missing | A second copy of a default at a call site drifts and hides a missing setting (D3) |

### Money and time

| Pattern | Why |
|---|---|
| Money in integer minor units (cents) or a fixed-precision decimal, never binary floating point | Float sums lose cents, and a credit or billing decision built on them is wrong with no error (D6) |
| Round once, explicitly, at a stated point | Rounding at several points gives totals that do not reconcile |
| Times are zone-aware and stored to the project standard; arithmetic through a timezone-aware library | Local-time arithmetic breaks twice a year and across regions (D6) |

### Concurrency and batch jobs

| Pattern | Why |
|---|---|
| A job that can overlap with itself holds a lock or is idempotent by key | Two overlapping runs otherwise double-write or race (D7) |
| A batch that stops midway leaves a known, safe state that the next run completes | Manual repair after a partial run is where data gets corrupted (D7) |
| Every safety guard (limit, abort, refusal) has a test that makes it trigger | An untested guard is a guess (D8) |

### Deviations and legacy code

| Pattern | Why |
|---|---|
| A knowing departure from a Hard rule is raised before it is committed; a comment is never the approval | A comment that admits a copy or an exception records a decision nobody approved (D11) |
| Existing code is not a precedent | Where the surrounding code and these standards disagree, new lines follow the standards and the old pattern is flagged (D12) |

---

## Anti-patterns (don't do these)

- **A second definition of a business rule** — re-deriving a calculation that already exists, here or in the system you read from (D2)
- **God classes / methods** — classes doing 7 things; methods 500 LOC long
- **Magic numbers without context** — `if ($status == 23)` with no clue what 23 means
- **Premature optimization** — micro-optimizing before profiling
- **Premature abstraction** — generalizing for use cases that don't exist
- **Comments that lie** — docstring says one thing, code does another (the worst kind)
- **Commented-out code** — delete it; git remembers
- **TODO / FIXME without ticket** — these accumulate forever; tie to an issue
- **Catch-all `try / catch` with empty body** — silently swallows the entire failure mode of the system
- **Global mutable state** — if avoidable, avoid it
- **Boolean parameters** — `doStuff(true, false, true)` is unreadable; use named options
- **Stringly-typed code** — passing things as strings that should be enums or typed values
- **Out parameters** — return values, don't mutate parameters (in languages where this matters)
- **Stale dependencies** — if you haven't updated the lockfile in a year, you have CVEs

---

## Stack-specific patterns

The universal patterns above apply everywhere. The patterns below apply when the change touches that stack.

### PHP

| Pattern | Why |
|---|---|
| Target PHP version matched in code | No PHP 8 syntax in PHP 7.4 targets; no PHP 7.4 deprecations in PHP 8 targets |
| Typed properties + return types where the version supports | Type system catches bugs; PHP 7.4+ supports typed props |
| `final` on non-extensible classes | Default; remove only for design-intentional subclassing |
| Namespaces for all new code | Avoid global-namespace classes |
| `require_once` not `include` | Errors should fail loud |
| Strict comparisons (`===`) where intent is identity | `==` is type-juggling; rarely what you mean |
| Null coalescing (`??`) over `isset() ? ... : ...` | Shorter, clearer |
| Typed exception hierarchy | Not `throw new Exception(...)` everywhere |
| PSR-12 formatting | Consistent across the codebase |
| Composer for dependencies | "Happens to be on the include path" is not declared dependency |
| No `eval` / `extract` / `assert` in production paths | All historical footguns |
| Avoid `$GLOBALS` mutation from deep code | Read at boundaries only |

### TypeScript / JavaScript / Next.js

| Pattern | Why |
|---|---|
| `strict: true` in tsconfig | Catches the bulk of type bugs |
| No `any` without a justifying comment | `any` is a controlled escape hatch, not a default |
| No `@ts-ignore` / `@ts-expect-error` without justification | Same |
| Public API types defined and exported | Inputs, outputs, errors |
| Server vs client component split intentional in Next.js | Data fetching server-side; interactivity client-side |
| `'use client'` only when state / effects needed | Bundle size matters |
| Client env vars must use `NEXT_PUBLIC_` prefix | And be set at build time |
| React keys are stable IDs (not array index for reorderable lists) | Render correctness |
| Strict ESLint + Prettier config | Style decisions are decided once, not per-PR |
| `next build` succeeds in CI | Catches dead routes, missing env vars, type errors |
| Suspense / error boundaries for async UI | Default fallback shouldn't be a white screen |
| `next/image`, `next/font`, etc. | Optimization is free when you opt in |

### SQL / Database

| Pattern | Why |
|---|---|
| Parameterized queries always | Universal — no language exception |
| Migrations: idempotent, reversible (or with documented rollback) | Production deploys need an out |
| Indexes verified via EXPLAIN | Adding an index that the planner doesn't use is no index at all |
| `ALTER TABLE` impact assessed before merging | Some `ALTER`s lock tables for minutes |
| Online migration patterns for large tables | PG: `CREATE INDEX CONCURRENTLY`; MySQL: pt-osc/gh-ost; SQL Server: online indexes |
| Constraint names explicit | Auto-generated names are unreadable in errors |
| `TIMESTAMPTZ` over `TIMESTAMP` (Postgres) where time is wall-clock-relevant | Timezone bugs are common; explicit is safer |
| Table naming follows the project convention | Consistency wins |
| Foreign-key names follow one convention | Consistent convention |
| Schema prefix in queries (`schema.table`) | Explicit, audit-friendly |
| Transactions sized to fit | Large multi-statement transactions block other writers |
| Audit rows for material changes | Who, what, when, before/after |

### Shell / DevOps / Scripts

| Pattern | Why |
|---|---|
| `set -euo pipefail` at top of bash | Fail fast on errors and undefined vars |
| Idempotent scripts (re-running is safe) | Operators retry; scripts should expect it |
| Explicit paths (`/usr/bin/curl` not `curl`) for cron / deploy | $PATH varies by env |
| Lock files for scripts that can't run concurrently | `flock` or equivalent |
| Logging via timestamped stdout/stderr | Cron captures both |
| Exit codes meaningful (0 success, non-zero variants) | Wrapping scripts depend on this |

### Front-end UI

| Pattern | Why |
|---|---|
| Accessibility from the start, not bolted on | Keyboard nav, ARIA labels, focus management, colour contrast |
| Responsive design tested at multiple breakpoints | 375 (mobile), 768 (tablet), 1280+ (desktop) |
| Loading states for every async operation | Default "blank screen" is unacceptable |
| Error states for every failure mode | Actionable error messages |
| Empty states designed | Zero-data screens are part of the UX |
| Forms validate inline AND on submit | Inline catches early; submit catches the rest |
| Tab order intentional | Forms should flow top to bottom |
| Performance budget per route | Time-to-interactive, bundle size targets |

---

## When the standards conflict

When two patterns conflict for a specific case:

1. Pick the one that makes the **code clearer to a future reader**
2. If still tied, pick the one that **fails faster**
3. If still tied, pick the one that **matches existing codebase style**

Document the choice in a comment if anyone might wonder later.

---

## How to apply

Apply these patterns while writing code, at every review depth; the review depth (`REVIEW_METHOD.md`) sets
how deeply the finished change is reviewed, not whether the patterns apply. The organization's release tier
governs release and production handling separately. Security patterns are never relaxed for a prototype.
