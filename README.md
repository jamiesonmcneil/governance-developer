# governance-developer

The shared **Developer role** for AI-assisted software development governance: how good software is
written, verified and reviewed, independent of any organization. It sits beside a shared core framework and
under each organization's own layers:

```
Shared core framework   (universal rules for every role)
  -> Organization / project layers   (systems, environments, production, data and provider decisions)
  -> Developer role (this repository), mandatory whenever development work happens
  -> Personal preferences
```

Precedence is the consuming framework's: the stricter applicable rule wins. This layer never weakens a rule
above it, and an organization may add strictness on top of it.

## Contents

| File | What it holds |
|---|---|
| `DEVELOPER_RULES.md` | D1 to D15, the Hard and Guideline semantics, and the lifecycle they produce |
| `REVIEW_METHOD.md` | Review depth (Low, Normal, High), author self-review, the logical-change boundary, how an independent review works when policy requires one, findings, rounds, reviewer failure, consult versus review, cost discipline |
| `VERIFICATION.md` | How a change is proven and how claims are worded |
| `COMPLETION_RECORD.md` | One record per logical change, at three depths |
| `CODE_REVIEW.md` | The reference checklist, loaded by surface |
| `DEVELOPMENT_STANDARDS.md` | The patterns behind the rules |
| `roles/dev.md` | The Developer role: may, must, must not |
| `tools/review-package.cjs` | Builds the smallest sufficient review package from these sources, secret-scans it, records the governance hash |
| `tools/review-run.cjs` | Runs one review through reviewers the organization injects; bounded retry, recorded fallback, normalized result, never a pass on failure |
| `tools/scan-code.py` | Deterministic code checks; everything advisory until an organization measures a rule and lists it as blocking |
| `tools/surfaces.json` | Default surface detection and section selection |

Run the tooling tests with `node tools/test/test-tools.cjs` (needs node, python3 and git).

## What belongs here, and what does not

**Here:** generic development method that would apply unchanged in any organization.

**Not here:** any organization's systems, infrastructure, environments, people, project paths, production
procedures, approved providers or models, credentials, data approvals, or review frequency. In particular,
**whether an independent review is required, and for which changes, is an organization decision**: this
layer defines how a review is done when one is required, not when.

Shared tooling stays generic: provider transports, credentials and model configuration belong to the
consuming organization, which injects them into `review-run.cjs`.

## Consuming this layer

1. Add it as a submodule of the organization's governance home (for example at `developer/`) and pin the
   commit, the same way the core framework is pinned.
2. Add its path to the organization's role directories so its units are part of the governed source set.
3. Make development activity load it automatically (an edit gate or equivalent), so no code is written
   without it, including after a context compaction.
4. In the organization layer, set the independent-review trigger, the approved reviewers, the data that may
   be sent to them, and the scanner rules that block.

Changes are made here, reviewed, and then picked up by each consumer with a gitlink bump. No consumer edits a
copy.

## Planned extensions

The layer is structured so later shared material can sit beside it without reshaping it: a software-delivery
workflow (branching, pull or merge requests, CI, quality and security gates, artifacts, promotion, release,
rollback and release evidence) and a QA and testing role. None of that is defined yet, and nothing here
assumes a particular branch model, CI system or deployment mechanism.

## Licence

MIT. See `LICENSE`.
