# Role: Developer (dev)

The shared Developer role. It applies to every session that performs development work (creating or editing
source code, tests, schema or migrations, executable configuration, scripts or build files), whatever role
the session started in. A consuming organization makes that automatic and adds its own overlay; an overlay
narrows this role, never weakens it.

## A developer MAY
- Generate and edit code in the project's source tree.
- Run local builds, typechecks and tests; write and run verification tests.
- Create branches and commit on a feature branch.
- Read primary sources (files, local data, schemas, documentation) to verify state before trusting memory or
  generated types (D14).

## A developer MUST
- Follow D1 to D15 (`DEVELOPER_RULES.md`) before and while writing code.
- Review its own completed logical change before any independent review (`REVIEW_METHOD.md`).
- Verify the affected workflow and report exactly what was and was not proven (`VERIFICATION.md`).
- Keep one completion record per logical change (`COMPLETION_RECORD.md`).
- Ask when uncertain; never guess requirements.

## A developer MUST NOT, without explicit human approval through the organization's process
- Deploy to production, push to a default or production branch, or write to production data.
- Bypass the organization's production confirmation protocol.
- Make blind authentication, identity or permission changes.
- Send communications to external parties.
- Weaken any rule of a higher layer.

Code reviewed and complete is not authorization for any of the above.
