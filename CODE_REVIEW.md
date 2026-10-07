# Code Review Reference

The canonical review checklist for the shared Developer role. It is a **reference loaded by surface**, not a
form to fill in: at a logical change's completion, the author (and any independent reviewer) loads only the
sections the change's surfaces select, at the depth `REVIEW_METHOD.md` sets. Nothing here is held resident
in full, and sections that cannot apply are not walked or marked.

Items marked *(guideline)* are heuristics under the Guideline semantics in `DEVELOPER_RULES.md`: a justified
departure is recorded, not approved. Every other item supports a Hard rule and a failure is a finding.

## Selecting sections

| Surface the change touches | Sections to load |
|---|---|
| Any code change at Normal or High | §1, §2, §3, §4, §5 |
| Tests added or changed | §7 |
| TypeScript, JavaScript, Next.js or React | §T |
| PHP | §P |
| SQL, schema or migrations | §11, §S |
| Authentication, authorization, sessions, permissions, tenant scope | §A, §3 |
| External integrations, webhooks, outbound HTTP, message queues | §I, §5 |
| Batch jobs, scheduled tasks, workers, imports | §B, §5, §8 |
| Money, prices, rates, quantities that are billed | §F |
| UI | §X |
| Large data, hot paths, loops over external calls | §8 |
| Logging, metrics, alerts | §9 |
| Configuration, environment, build or deployment files | §10, §12 |
| High depth, any surface | §13 (adversarial pass), in addition to the above |

At **Low** depth no section is loaded: D1 to D15 and the mechanical and test results are the review.

## §1 Baseline

| # | Check |
|---|---|
| 1.1 | Compiles and typechecks; linters pass |
| 1.2 | Existing tests pass, including ones not obviously related |
| 1.3 | New or changed behavior has tests in proportion to risk (D8) |
| 1.4 | The affected workflow was verified as `VERIFICATION.md` describes, and the record says exactly what was and was not reached (D9, D10) |
| 1.5 | No new lint or build warnings |
| 1.6 | Debug artefacts removed (stray prints, dumps, breakpoints, scratch code) |
| 1.7 | The diff holds one concern; no unrelated changes mixed in |

## §2 Configuration and hard-coded values (D3, D4)

| # | Check |
|---|---|
| 2.1 | No hard-coded URLs, hosts or endpoints in runtime code |
| 2.2 | No hard-coded identifiers (accounts, users, records, environments); any numeric literal of three or more digits is justified |
| 2.3 | No credentials, keys or tokens, including placeholders that look real |
| 2.4 | Magic numbers carry a comment explaining the value *(guideline)* |
| 2.5 | Required configuration fails loudly when missing; no silent fallback to a value that works somewhere else |
| 2.6 | Each default is defined once, in the configuration source, not repeated at call sites |
| 2.7 | No environment-specific values in shared code or build artefacts |
| 2.8 | Where a wrong environment pairing could cause harm, the code checks environment identity before acting and fails closed (D4) |

## §3 Security (D5)

| # | Check |
|---|---|
| 3.1 | Queries are parameterized; no string-built SQL, even with "trusted" input |
| 3.2 | Input validated at trust boundaries (requests, files, messages, external data) |
| 3.3 | Output encoded for its destination (HTML, JSON, URL, shell) |
| 3.4 | Public identifiers are unguessable (UUIDs, slugs), never sequential keys |
| 3.5 | Every read and write of scoped data is filtered by the caller's tenant or owner |
| 3.6 | Identity and scope come from the authenticated session, never from input |
| 3.7 | Possession of an identifier is never treated as authorization |
| 3.8 | Tokens, share links and reset codes are cryptographically random, checked for expiry and revocation |
| 3.9 | Secrets and protected personal data never reach logs, error responses or client bundles |
| 3.10 | State-changing endpoints are protected against cross-site request forgery |
| 3.11 | Public endpoints that can be called in a loop are rate-limited |
| 3.12 | Uploads are validated for type, size and content, and stored safely |
| 3.13 | Dependencies have no known vulnerabilities; new dependencies exist and are maintained (D14) |
| 3.14 | No user-, model- or data-supplied code is executed; no unsafe deserialization |
| 3.15 | Server-side requests go only to destinations the code names, never a caller-chosen URL |
| 3.16 | TLS verification stays enabled |
| 3.17 | Least privilege: application database logins are not superusers; shared stores enforce isolation in the database as well as the application |
| 3.18 | Private data stays out of AI calls, logs, exports and search |
| 3.19 | A new data interface has a second-account test: another account cannot read, change or infer the data |

## §4 Reuse and structure (D1, D2, D13)

| # | Check |
|---|---|
| 4.1 | The change reuses or consumes the existing implementation of every helper, query and integration it needs (D1) |
| 4.2 | No second definition of a business rule or calculation; any necessary replication is explicit, justified, tested against the authority and approved when material (D2) |
| 4.3 | No copy-paste blocks |
| 4.4 | Functions do one thing; long methods (about 50 lines soft, 100 hard) and files (about 300 soft, 500 hard) are split *(guideline)* |
| 4.5 | More than four positional parameters become an options object *(guideline)* |
| 4.6 | No speculative abstraction; extraction where reuse exists, a boundary is clear, or a near-term shared need is strong *(guideline, D13)* |
| 4.7 | One name per concept across the codebase |
| 4.8 | A poor surrounding pattern was not copied; a conflicting legacy pattern is flagged (D12) |

## §5 Errors and resilience (D7)

| # | Check |
|---|---|
| 5.1 | No empty catch; every catch handles, transforms or rethrows |
| 5.2 | Retryable and non-retryable failures are distinguished |
| 5.3 | Retries have a budget with backoff; never infinite |
| 5.4 | Operations that can be repeated are idempotent in fact |
| 5.5 | Concurrent execution was considered (locks, unique constraints, compare-and-set) |
| 5.6 | Partial failure leaves a known, recoverable state |
| 5.7 | Timeouts on every external call and long operation |
| 5.8 | Resources are released on failure |
| 5.9 | Error messages carry context for operators and leak nothing internal to users |

## §6 Naming and readability *(guideline)*

| # | Check |
|---|---|
| 6.1 | Names express intent; booleans read as questions |
| 6.2 | Comments explain why, not what; no commented-out code; TODOs carry a ticket |
| 6.3 | No dead code |
| 6.4 | Complex logic has a short explanation of the approach |
| 6.5 | Style matches the file and the project conventions |

## §7 Tests (D8, D9)

| # | Check |
|---|---|
| 7.1 | Tests are named for behavior and independent of each other and of run order |
| 7.2 | Failure paths and edge cases are covered, not only the happy path |
| 7.3 | Safety guards have tests that make them trigger |
| 7.4 | A bug fix has a test that failed before the fix |
| 7.5 | Test data can reach the behavior claimed (D9) |
| 7.6 | Mocks sit at boundaries the project does not own; the code under test is not mocked |
| 7.7 | Tests do not depend on production systems or real customer data |

## §8 Performance

| # | Check |
|---|---|
| 8.1 | No N+1 queries or loops of remote calls |
| 8.2 | Large iterations stream or page; memory is bounded |
| 8.3 | Complexity fits the realistic input size |
| 8.4 | Indexes exist for the query shapes and are used (checked with the query plan) |
| 8.5 | Caches have a TTL and a size cap |

## §9 Observability

| # | Check |
|---|---|
| 9.1 | Errors are always logged, with correlation identifiers |
| 9.2 | Log payloads are bounded and redacted at one tested boundary |
| 9.3 | Key counters are measurable; alerts fire only on meaningful failures |
| 9.4 | Health checks check something real |

## §10 Configuration management

| # | Check |
|---|---|
| 10.1 | All configuration comes from one source per value |
| 10.2 | Secrets come from the secret store or environment, never code, and never beside their encryption key |
| 10.3 | New configuration keys are documented with what they control and why their default |
| 10.4 | Defaults are safe: error rather than guess |

## §11 Data layer

| # | Check |
|---|---|
| 11.1 | Schema changes have a migration; it is idempotent and has a rollback or documented recovery |
| 11.2 | The migration was run against populated, production-shaped data |
| 11.3 | Identifiers, nullability and types were verified from the live schema (D6, D14) |
| 11.4 | Foreign keys and hot query shapes are indexed |
| 11.5 | No `SELECT *` in application code |
| 11.6 | Material data changes are audited (who, what, when, before and after) |
| 11.7 | Destructive operations have a verified backup first |
| 11.8 | Long statements have a timeout; transactions are sized to avoid blocking writers |

## §12 Deployment and operability

| # | Check |
|---|---|
| 12.1 | Backwards compatibility for at least one release, or a coordinated cutover |
| 12.2 | High-risk behavior sits behind a flag or a staged rollout |
| 12.3 | A rollback path exists with exact steps |
| 12.4 | Deployment does not overwrite environment-held configuration |
| 12.5 | Documentation and runbooks are updated |

## §13 Adversarial pass (High depth)

One written sentence for each question that applies:

1. What would the most experienced developer on this codebase call out first?
2. What breaks at ten times the load or a hundred times the rows?
3. What happens during a network partition or a downstream outage, and what state is left?
4. What happens when an upstream shape changes?
5. What is the worst case in front of the most hostile stakeholder (an auditor, an attacker, a regulator)?
6. Did we already have this code (D1, D2)?
7. Is anything clever rather than obvious?
8. What would a reader in six months wrongly assume this code does?
9. If this is reverted, what state is left behind?
10. What would an on-call engineer need at 2am that is missing?

## §A Authentication, authorization and scope

| # | Check |
|---|---|
| A.1 | Every protected route, resolver, job and tool enforces authentication itself; verified with an unauthenticated request |
| A.2 | Authorization is checked at the boundary that owns the resource, after the lookup, for both source and target of moves and copies |
| A.3 | Tenant or owner scope comes from the session and is applied to every query and join |
| A.4 | Denied, forged, expired and cross-tenant cases are tested (`VERIFICATION.md`) |
| A.5 | Public, unscoped reference data is not given meaningless ownership checks (D5) |
| A.6 | Session and token changes consider revocation, expiry and replay |

## §I Integrations

| # | Check |
|---|---|
| I.1 | The external interface was verified from its documentation or a real call, not memory (D14) |
| I.2 | Environment pairing is checked: test talks to sandbox, production to production, and a mismatch fails closed (D4) |
| I.3 | Timeouts, bounded retries with backoff, and idempotency keys where the remote side supports them |
| I.4 | Partial failure is recoverable: what was sent, what was confirmed, what is retried |
| I.5 | Inbound webhooks verify signatures and tolerate duplicates and reordering |
| I.6 | Representative non-production data exercised the claimed cases |

## §B Batch jobs, schedules and workers

| # | Check |
|---|---|
| B.1 | Re-running the job is safe (idempotent) |
| B.2 | Concurrent runs are prevented or safe (a lock or a unique claim) |
| B.3 | A failure mid-run leaves a resumable state and is visible to operators |
| B.4 | Work is bounded per run, with a time budget |
| B.5 | Progress and outcome counts are logged |

## §F Money and financial values (D2, D6)

| # | Check |
|---|---|
| F.1 | Money uses integer minor units or fixed-precision decimal, never binary floating point |
| F.2 | Rounding mode and the point of rounding are explicit and match the authoritative definition |
| F.3 | Currency is carried with the amount |
| F.4 | The calculation consumes or reuses the authoritative definition (D2), and tests compare against it |
| F.5 | Tests include rounding boundaries, zero, negatives and refunds as applicable |

## §P PHP

| # | Check |
|---|---|
| P.1 | Code matches the target PHP version; `php -l` clean with that version |
| P.2 | Typed properties, parameters and returns where the version supports them |
| P.3 | `final` by default; namespaces on new classes; `require_once` over `include` |
| P.4 | Strict comparisons where identity is meant; null coalescing over `isset` ternaries |
| P.5 | A typed exception hierarchy |
| P.6 | Dependencies declared through Composer |
| P.7 | No `eval`, `extract`, `assert` or `unserialize` on untrusted input; no deep `$GLOBALS` mutation |

## §T TypeScript, JavaScript and Next.js

| # | Check |
|---|---|
| T.1 | Strict mode; no unexplained `any`, `@ts-ignore` or `@ts-expect-error` |
| T.2 | Public input and output types are defined and exported |
| T.3 | Server and client split is deliberate; client code only where state or effects need it |
| T.4 | Client-side environment values are set at build time and contain nothing secret |
| T.5 | Stable keys for lists that can reorder |
| T.6 | Production build succeeds, not only the dev server |
| T.7 | Error boundaries where asynchronous UI can fail |
| T.8 | Client bundle impact of new dependencies considered |

## §S SQL and schema

| # | Check |
|---|---|
| S.1 | The migration runs cleanly on an empty and on a populated database |
| S.2 | Lock impact assessed; online patterns for large tables |
| S.3 | Generated migrations were read |
| S.4 | `UPDATE` and `DELETE` without `WHERE` are rejected |
| S.5 | Index and constraint names are explicit |
| S.6 | Timestamps are timezone-aware where wall-clock time matters |
| S.7 | Sensitive columns are marked or encrypted |

## §X User interface

| # | Check |
|---|---|
| X.1 | Accessibility: keyboard navigation, labels, focus, colour contrast |
| X.2 | Loading, empty and error states exist |
| X.3 | Behavior at mobile, tablet and desktop widths |
| X.4 | Dark mode, where supported |
| X.5 | Supported browsers |
| X.6 | Locale-aware dates, numbers and currency where applicable |

## Automation

Compilers, linters, dependency audits, secret scanners and the code scanner make the mechanical items
cheap. They run before the author's review and never replace it.
