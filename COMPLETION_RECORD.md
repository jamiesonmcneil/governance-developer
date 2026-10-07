# Completion Record

One record per **logical change**, not per commit. It is the author's self-review result and the evidence
an independent reviewer checks. Keep it short: a Low change gets a few lines. Write it where the consuming
organization keeps such records (a pull request description, a file beside the change, the session log or
the tracker).

## Low

```
Change: <id or short name>
Depth: Low (<why: the surfaces touched>)
Diff: <commit range or branch>
D1-D15: no departures | <departure and how it was handled>
Mechanical: <build / typecheck / lint / scanners: result>
Tests: <what ran, where, result>
Independent review: <not required by policy | provider, model, verdict>
Findings: <none | id: valid, fixed / invalid, reason>
```

## Normal

```
Change: <id or short name>
Depth: Normal (<surfaces touched>)
Diff: <commit range or branch>
D1-D15 self-check: <one line per rule that applies; "no departures" for the rest>
CODE_REVIEW sections applied: <sections, and what each found>
Mechanical: <build / typecheck / lint / scanners: result>
Tests: <what ran>
Environment and data: <where; which data>
Cases exercised: <list>
Cases not exercised: <list, with why>
Independent review: <not required by policy | provider, model, round, verdict>
Finding dispositions: <id: valid, fixed and verified how | invalid, evidence>
Remaining risks: <none | list>
```

## High

Everything in Normal, plus, for the affected surfaces only:

```
Adversarial pass: <CODE_REVIEW section 13 answers that apply, one sentence each>
Deeper evidence: <for each High surface: the allowed / denied / forged / cross-tenant results, the
                  migration on empty and populated data with rollback, the financial cases with rounding,
                  the integration run on representative data, as applicable>
Rollback: <how the change is undone and what state it leaves>
```

## Rules for the record

- The record states evidence, not intentions (`VERIFICATION.md` section 3).
- "Cases not exercised" is never left out because it is empty: write "none" when none.
- Every finding from an independent review gets a disposition before the change is called complete.
- No item-by-item "N/A" lists for checklist sections that cannot apply.
