# Backend feature queue

This directory is the executable roadmap for backend work that is **not yet**
covered by an approved implementation spec under `specs/`.

Its main purpose is to save OMP/model budget. The agent must not rediscover
already-known boundaries or debate features that are explicitly blocked.

## Execution rule

For each run:

1. Read `PROJECT_STATE.md` and this queue.
2. Pick the first item that is allowed to advance.
3. Read only that feature brief and its listed authoritative inputs.
4. Do not reopen fixed decisions.
5. Do not design or implement a feature marked `BLOCKED`.
6. For `READY_FOR_SPEC`, produce only the missing spec/decision packet; do not
   create implementation code until the feature becomes
   `READY_FOR_IMPLEMENTATION`.
7. Existing merged specs 001–004 remain authoritative for shipped behavior.

## Queue

| Order | Feature | Status | Main blocker/dependency |
|---|---|---|---|
| 1 | [BE-005 Subscription core and paid entitlement](BE-005-subscriptions-core.md) | MERGED | Shipped in PR #13 after ADR 0009 approval |
| 2 | [BE-006 Payment provider integration](BE-006-payment-provider.md) | MERGED | Shipped in PR #14 (Robokassa MVP) |
| 3 | [BE-007 Progress/dashboard aggregate API](BE-007-progress-dashboard.md) | MERGED | Dashboard aggregate merged |
| 4 | [BE-008 Profile and study preferences](BE-008-profile-preferences.md) | READY_FOR_REVIEW | Profile and study preferences implemented |
| 5 | [BE-009 Content bulk/import extensions](BE-009-content-bulk-import.md) | BLOCKED | bulk identity/removal/workflow semantics not accepted |
| 6 | [BE-010 Slug-based public URLs](BE-010-slug-public-urls.md) | BLOCKED | uniqueness/collision/redirect policy unresolved |

## Token-saving rule

A feature brief is the planning boundary. The manager should not spend a
planning pass exploring unrelated architecture.

For a `READY_FOR_SPEC` feature, PLAN means:

- confirm the listed source facts against current `main`;
- fill the spec structure around those facts;
- surface only the explicitly listed unresolved owner decisions;
- stop before implementation if those decisions are still unresolved.

For an implementation-ready feature, PLAN should be a compact module/file zone
plan, not a second specification.

Do not create scout/reviewer swarms merely to confirm that a documented blocker
is still a blocker.
