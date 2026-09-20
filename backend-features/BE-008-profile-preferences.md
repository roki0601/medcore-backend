# BE-008 — Profile and study preferences

Status: BLOCKED

## Why blocked

The prototype mentions university, course, semester goal, daily load and
selected subjects, but accepted backend sources explicitly leave profile/study
preferences unresolved.

Do not infer persistence fields from the prototype.

## Owner decisions required

Before a spec:

- confirm whether study preferences are in MVP;
- exact fields to persist;
- which fields are optional;
- whether university/course are free text or references/enums;
- whether "selected subjects" is a persistent relation or just catalog UI;
- update permissions;
- privacy/export/delete semantics;
- whether these fields live directly on User or in a separate profile model.

## Fixed boundaries

- Telegram auth identity fields stay separate from study preferences;
- do not make optional profile data required for login;
- self-service account deletion rules must cover the accepted profile data;
- do not expose profile fields publicly by default.

No code should be created while this remains BLOCKED.
