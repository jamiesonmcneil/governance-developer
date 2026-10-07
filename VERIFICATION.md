# Verification

How a development change is proven, and how the proof is reported. D8, D9 and D10 are the rules; this file
is how they are met. A consuming organization adds its own test tooling (frameworks, environments,
browser automation, test accounts) in its own layer.

## 1. Verify the workflow the change affects

Verification exercises the actual affected workflow, at the level the change can affect. Match the check to
the change:

| The change | What verification means |
|---|---|
| UI | The rendered result and the user flow, in a real browser where behavior is interactive |
| Persisted data | The write, then a reload or read-back that shows the stored state |
| An integration | Representative non-production data that reaches the claimed cases, end to end |
| A utility or helper | Focused tests plus the real caller path that uses it |
| Authentication or authorization | The allowed case, the denied case, a forged or tampered input, and a cross-tenant or cross-account attempt, as applicable |
| A schema or migration | A run on an empty and on a populated database, the rollback or the documented recovery, and the code that reads the new shape |
| A tiny presentation change | The built and rendered result |

Do not run checks that cannot exercise the change just to say they ran (no end-to-end theater for a typo),
and never skip a check that can. Build, typecheck and lint always run for code.

## 2. Test data must reach the claim (D9)

Before calling a behavior tested, check that the data used could exercise it:

- a test that passes on empty data proves nothing about non-empty data;
- a filter tested only with rows that all match proves nothing about exclusion;
- a guard tested only on the allowed path proves nothing about the guard (D8: safety guards are tested by
  making them trigger);
- a calculation tested only on round numbers proves nothing about rounding.

Where the available data cannot reach a relevant case, say so (section 3). Building data that does reach it
is better than saying so, where it is practical and safe.

## 3. Claims are exact (D10)

"Tested", "verified", "works", "works in dev", "complete", and any verification level the governing
framework defines, are never used beyond the evidence. Every testing or status report states, as applicable:

1. **What ran:** the commands, test files or manual steps.
2. **Where:** local, a development environment, staging, production (read-only), and which build or commit.
3. **What data:** fixtures, synthetic data, an anonymized copy, a named test account.
4. **Cases exercised:** the specific behaviors that were reached.
5. **Relevant cases not exercised:** and why (no data, no environment, out of scope).

Partial verification is reported as partial. "I changed it but could not verify X because Y" is an
acceptable report; "done" without the evidence is not.

## 4. Failures and regressions

- A bug fix starts with a failing test that reproduces it, where practical (D8), and the test is kept.
- Existing tests are run, not only the new ones; a test that starts failing is investigated, never deleted
  or weakened to pass.
- A flaky result is not a pass.

## 5. Where verification sits in the lifecycle

Verification comes before the author's final self-review is recorded and before any independent review
(`REVIEW_METHOD.md`), so the reviewer checks real evidence rather than intentions. After review fixes, the
affected checks and tests run again.
