# Development Core Rules (D1 to D15)

The rules every development session follows while it writes code. They are the core of the shared Developer
role: active before the first edit and for as long as development work continues. They replace weaker,
overlapping development-floor rules in a consuming organization rather than sitting beside them.

How the rest of this layer uses them: `REVIEW_METHOD.md` (review depth, author self-review, independent
review when required), `VERIFICATION.md` (how behavior is proven and how claims are worded),
`COMPLETION_RECORD.md` (one record per logical change), `CODE_REVIEW.md` (the reference checklist, loaded by
surface), `DEVELOPMENT_STANDARDS.md` (patterns).

## Hard rules and guidelines

**HARD.** A Hard rule is followed. A knowing, material departure from a Hard rule stops the work and goes
through the consuming organization's governance approval process before the work continues (D11). A comment
in the code is never that approval.

**GUIDELINE.** A guideline is the expected default. A departure is allowed when it is justified in the
change (a sentence in the completion record or a code comment explaining why), without an approval step.
Heuristics such as method length, parameter count, file length and abstraction rules of thumb are guidelines:
they become an approval matter only when the departure creates a material issue (a Hard-rule violation, a
security or data risk, or code that cannot be reviewed).

## The rules

### D1 — Search before writing — HARD

Read the code being changed before editing it.

Before creating a helper, query, calculation, business rule, integration implementation or reusable function, search:

- the current codebase;
- shared utilities;
- authoritative systems/sources where applicable.

Use or consume what already exists where appropriate.

### D2 — One authoritative business definition — HARD

A business rule or calculation has one authoritative definition.

Reuse its implementation where technically appropriate.

Across system boundaries, prefer consuming the authoritative result.

If replication is genuinely necessary, it must be:

- explicit;
- justified;
- tested against the authority;
- approved when material.

Do not create a second definition merely because doing so is locally easier or faster.

### D3 — Configuration has one authoritative home — HARD

Configurable/environment-specific endpoints, URLs, hosts, identifiers, master-data references and defaults come from authoritative configuration.

Defaults are defined once and not repeated at call sites.

Required configuration fails loudly when missing.

True invariant/domain constants may remain in code when genuinely part of program semantics rather than deployment configuration.

### D4 — Environments never cross accidentally — HARD

Where code communicates between systems/environments and incorrect pairing could cause harm, verify compatible environment identity before the relevant operation.

Development/test must not accidentally write to production.

Production must not accidentally write to sandbox/test.

Fail closed when compatibility cannot be established.

### D5 — Security is implemented, not added during review — HARD

As applicable:

- validate input at trust boundaries;
- parameterize queries;
- enforce authentication/authorization;
- enforce tenant/resource scope;
- do not infer authorization from possession of an identifier;
- constrain outbound destinations;
- protect credentials;
- keep TLS verification enabled;
- never dynamically execute untrusted input;
- never use unsafe deserialization.

Protected/scoped resources require authorization at the appropriate boundary.

Do not mechanically apply meaningless ownership checks to genuinely public/unscoped data.

### D6 — Correct types and semantics — HARD

Use domain-appropriate types.

Examples:

- money uses integer minor units or fixed-precision decimal as appropriate;
- time handling is timezone-aware and follows project standards;
- identifiers, nullability and data shapes are verified from authoritative schema/source.

Do not guess.

### D7 — Design for real failure — HARD

Where applicable address:

- retries/retry budgets;
- idempotency;
- concurrency;
- partial failure;
- timeouts;
- rollback/recovery.

Errors must be useful and safe.

Logs must not expose secrets or protected personal information.

### D8 — Tests prove behavior — HARD

Changed behavior gets appropriate tests.

Failure paths matter.

Bug fixes begin with a reproducing failing test where practical.

Important safety guards must have tests that make them trigger.

### D9 — Test data must support the claim — HARD

Never claim behavior was tested if the available data could not exercise it.

Relevant cases that were not exercised must be explicitly stated.

### D10 — Testing/status claims are exact — HARD

Words such as:

- tested;
- verified;
- works;
- works in dev;
- complete;

must never exceed evidence.

Testing/status reports identify, as applicable:

- what ran;
- where;
- what data;
- cases exercised;
- relevant cases not exercised.

### D11 — Hard rules cannot be waived in comments — HARD

A comment acknowledging a rule violation is not approval.

A knowing material Hard-rule departure stops work and follows the applicable governance approval process.

### D12 — Existing code is not automatically precedent — HARD

Do not propagate a poor legacy pattern merely because surrounding code uses it.

New code follows current standards unless there is a legitimate technical constraint.

Flag conflicting legacy patterns instead of silently copying them.

### D13 — Build for the current requirement — GUIDELINE

Prefer clear, cohesive and maintainable code.

Do not create speculative abstractions for hypothetical callers.

Extract/reuse where:

- reuse exists;
- an architectural boundary is clear;
- a strong near-term shared need exists.

Avoid duplication and unnecessary abstraction.

### D14 — Verify interfaces rather than inventing them — HARD

When uncertain, verify:

- APIs;
- methods/functions;
- packages;
- configuration keys;
- tables;
- columns;
- schemas;
- external-system behavior;

from source, schema, documentation or actual execution.

Do not invent interfaces from model memory.

### D15 — Done means reviewed — HARD

A logical code change is not considered complete until:

1. applicable build/type/lint checks pass;
2. applicable tests and real verification pass;
3. the author performs the required proportional governance/code review;
4. testing and verification evidence accurately states what was and was not proven;
5. any independent review required by the governing Org/Project policy is completed;
6. valid blocking findings are resolved and verified.

## The development lifecycle these rules produce

Developer rules active → implement correctly → mechanical checks → author self-review → real verification
→ independent review where the governing policy requires one → resolve valid findings → complete →
separate release and production controls.

Code being complete is never authorization for a release or a production action. Those stay under the
consuming organization's release and production gates.
