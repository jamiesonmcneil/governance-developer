# Review Method

How a logical code change is reviewed: by its author first, and by an independent reviewer when the
governing organization or project policy requires one. This file defines the method. **It does not decide
when an independent review is required, which reviewers or providers may be used, or what data may be sent
to them.** Those are organization decisions and live in the consuming organization's own layer.

## 1. The review boundary is the logical change

- A **logical change** is one coherent unit of delivered behavior: a feature, a fix, a refactor, a schema
  change with the code that uses it. It may span many commits.
- Review happens at the **completion boundary**: when the author is about to call the change complete,
  before it merges to a long-lived branch, and before release or deploy where those apply. Never per commit.
- Experimental or throwaway code that is not being declared complete is not reviewed yet. If it becomes
  deliverable code, it goes through this method before it is approved, merged or released.

## 2. Review depth: Low, Normal, High

Depth is set by the **surfaces the change actually touches**, not by the release tier of the system it
lives in. A production system can contain Low, Normal and High changes. Release tier continues to govern
release, deployment and production controls; review depth governs how deeply the change itself is reviewed.
When unsure between two depths, use the higher one.

| Depth | Typical changes | Author self-review | Independent reviewer receives (when one is required) |
|---|---|---|---|
| **Low** | A label or text change in code, trivial styling, a tiny no-logic refactor, a tiny safe correction | D1 to D15, mechanical checks, applicable build and tests, a concise self-review | The small final diff, D1 to D15, the relevant build and test result. No CODE_REVIEW sections |
| **Normal** | An ordinary feature, a bug fix, API behavior, a normal refactor, ordinary application logic | D1 to D15, deterministic checks, applicable tests, the applicable CODE_REVIEW sections, a concise completion record | The final diff, D1 to D15, the applicable CODE_REVIEW sections, the completion record and test evidence |
| **High** | Authentication or authorization, tenant isolation, financial calculations, schema or migrations, production data, significant integrations, security or privacy, architecture, destructive operations, a major refactor, consequential production functionality | Everything for Normal, plus all applicable CODE_REVIEW sections, the adversarial pass, and deeper verification evidence for the affected surfaces | Everything for Normal, plus the adversarial material and the deeper evidence for the affected surfaces |

A change touching any High surface is High, whatever its size.

## 3. Author self-review comes first, always

The author is responsible for producing compliant code. The sequence is:

1. follow D1 to D15 while implementing;
2. run the mechanical checks (build, typecheck, lint, the organization's scanners);
3. run the applicable tests and the real verification (`VERIFICATION.md`);
4. review the change against D1 to D15 and the applicable CODE_REVIEW sections for its depth;
5. fix everything the author finds;
6. write the completion record (`COMPLETION_RECORD.md`) with exact evidence (D9, D10).

Only then does an independent review start, if one is required. An independent reviewer exists to catch
what the author missed. It is never the mechanism that finds ordinary mistakes the author should have
caught: "write code, then ask another model whether it is good" is not this method.

## 4. Independent review, when policy requires one

### 4.1 Defaults

- **One reviewer, one round.** No panel, no debate, no repeated full review.
- **Independent of the author.** Where the reviewer is an AI model, it comes from a different model family
  or provider than the model that wrote the change, so the two do not share the same blind spots.
- **Focused context.** The reviewer receives only what it needs (section 4.2). Never the whole governance
  framework and never the whole repository.
- **The same governance the author followed.** The review package is built from the canonical governance
  sources at review time. No reviewer-specific or vendor-specific copy of the rules exists or is maintained.
  A transport wrapper may format the request for a given provider; the rules it carries are the shared ones.

### 4.2 The review package

Built by a package builder from canonical sources, in this order:

1. D1 to D15 and the Hard and Guideline definitions;
2. the review depth and the surfaces that set it;
3. only the CODE_REVIEW sections that apply to those surfaces (none at Low);
4. the applicable organization and project rules (selected by section, never whole layers);
5. the final logical diff;
6. the author's completion record (self-review result);
7. the test and verification evidence;
8. any source context needed to understand the diff, selected file by file.

The package records the governance version or hash it was built from, the files included and the files
excluded with the reason.

**Package safety.** The exact material being transmitted is secret-scanned before it leaves the machine. A
positive finding blocks transmission: the offending content is removed or the file excluded, and the package
is rebuilt and scanned again. Masking a known secret in place and sending anyway is not allowed. Environment
files, key files, secret-store or vault contents, credentials and unrelated files are never included.
Customer or private data is included only where the governing policy permits it and the review genuinely
needs it. What may be sent, and to whom, is the organization's decision.

### 4.3 What the reviewer is asked to do

The reviewer reviews the change against the supplied governance, not in general. It is asked to challenge:

1. D1 to D15 violations;
2. violations of the supplied CODE_REVIEW sections;
3. duplicated or reimplemented existing functionality or business rules;
4. completion or testing claims the evidence does not support;
5. tests whose data could not exercise the claimed behavior;
6. configuration and source-of-truth violations;
7. environment-crossing risk;
8. authentication, authorization, security, tenant and data risks;
9. concurrency, retry, idempotency and partial-failure issues where applicable;
10. other material violations of the supplied standards.

It returns actionable findings, not an essay.

### 4.4 The normalized result

Whatever the reviewer's raw output, the tooling normalizes it to:

- **verdict:** `PASS`, `PASS_WITH_FINDINGS` or `FAIL`;
- **findings**, each with: severity (`blocking`, `major`, `minor`), rule ID (for example `D3` or a CODE_REVIEW
  item), file and location, the issue, the evidence, the required action.

A blocking finding makes the verdict `FAIL` whatever the reviewer called it. A response that cannot be
normalized is not a pass.

### 4.5 Handling findings

The author evaluates every finding independently. Reviewers are not obeyed blindly.

- **Valid:** fix it.
- **Invalid:** record why, with evidence (the code, the test, the governance text).
- **A Hard-rule departure the author believes is justified:** follow the governing approval process (D11).

After fixes: rerun the affected mechanical checks, the affected tests and the affected self-review items,
and verify that each specific finding is resolved. Record the disposition of every finding in the completion
record. A fix does not trigger another full external review.

### 4.6 A second round, only when

A second independent review runs only when:

1. the first review found a material architecture, security or data issue;
2. the fix materially changed architecture, data flow, an interface, a schema, authentication or authorization, or environment behavior;
3. deterministic verification cannot close a material finding;
4. another formal gate independently requires a re-check;
5. the owner explicitly requests another review.

A second round is **delta-focused**: the relevant original findings, the resulting change, the applicable
governance and the updated evidence. The original package is not resent unless genuinely necessary. **A
third round requires the owner's explicit approval.**

### 4.7 More than one reviewer

A second, different reviewer is used only when there is material reviewer uncertainty or disagreement, when
a High-risk issue genuinely warrants another independent perspective, when the first reviewer is
unavailable (section 4.8), or when the owner explicitly asks for it.

### 4.8 Reviewer failure

If the selected reviewer fails:

1. retry a bounded number of times for a transient failure (timeouts, rate limits, server errors);
2. then use the next reviewer the governing policy already approves;
3. record the substitution and the reason.

A failed, unavailable or unparseable review is never a pass. A change that requires an independent review
is not complete until one has succeeded.

## 5. Consult is not review

- **Consult:** an optional, advisory exchange with one or more models during planning, research, design or
  a disagreement. It may use several models.
- **Formal code review:** a completion gate run after author self-review, against the canonical governance,
  one reviewer by default.

A consult earlier in the task does not satisfy the formal review. A model that took part in a design
consult may still be the reviewer, but its earlier answer is not evidence that the implementation is
correct.

## 6. Cost and context discipline

- One reviewer, one round, focused rules, focused diff, focused evidence by default.
- Low reviews are deliberately tiny.
- Record tokens or cost where the tooling already makes that practical; do not build an accounting system.
- An independent review does not authorize a release or a production action. Code approved is not
  production action approved.

## 7. What the consuming organization decides

Set in the organization or project layer, never here:

- when an independent review is required (for example: never, High only, or every logical change);
- whether the reviewer is a person, an AI model or either, and which providers and models are approved;
- what source and data may be sent to an external reviewer, with the organization's data approval;
- the reviewer selection policy (a configured default, rotation, capability, availability), retry budget
  and fallback order;
- the organization's scanner thresholds and which checks block.
