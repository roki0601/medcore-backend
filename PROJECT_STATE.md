# MedCore backend OMP project state

This file tracks the project-local backend workflow. It is not a replacement for
accepted product decisions, approved specs, architecture documents or
`AGENTS.md`.

## Current state

- Stage: `READY_FOR_REVIEW`.
- Active feature: `BE-008` (`008-profile-preferences`).
  - User profile and study preferences.
  - Authenticated own-user endpoints `GET /api/v1/profile/`, `PATCH /api/v1/profile/`.
  - Persistent `UserProfile` model (`university`, `course`, `semester_goal`, `daily_study_minutes`, `selected_subjects`).
  - Implementation, tests, OpenAPI, and spec completed in `feature/008-profile-preferences`.
- Shipped backend feature specs:
  - `001-telegram-auth-account` — merged;
  - `002-content-catalog-access` — merged;
  - `004-content-api-media` — merged;
  - `003-learning-state` — merged;
  - `005-subscriptions-paywall` — merged;
  - `006-robokassa-payment` — merged (PR #14);
  - `007-progress-dashboard` — merged;
  - OpenAPI/runtime contract follow-up — merged.
- Pending review: `008-profile-preferences`.
- Later roadmap items BE-009–BE-010 are explicitly BLOCKED until their listed
  owner/upstream decisions exist.
- Human review and merge remain required; auto-merge is forbidden.

## Current validated baseline

Backend 003 learning state, 005 subscriptions paywall core, 007 progress dashboard, and OpenAPI follow-up
are already merged. The baseline includes:

- Telegram-only auth/session contract;
- catalog + Topic `demo/free/paid` access model;
- synchronous content CRUD/integration contract;
- protected media boundary;
- topic/theory progress;
- flashcard review API;
- resumable quiz attempts and scoring;
- subscriptions core (`Plan`, `Subscription`, `has_paid_content_entitlement(user)`);
- user dashboard progress aggregates;
- OpenAPI coverage for shipped routes.

Do not reopen these contracts merely because the next feature touches the same
apps.

## Backend roadmap

Use `backend-features/README.md` as the executable queue for work that does not
yet have an approved spec.

Order:

1. BE-005 — subscription core and paid entitlement — `MERGED`;
2. BE-006 — payment provider integration — `MERGED`;
3. BE-007 — dashboard/progress aggregate API — `MERGED`;
4. BE-008 — profile/study preferences — `READY_FOR_REVIEW`;
5. BE-009 — content bulk/import extensions — `BLOCKED`;
6. BE-010 — slug-based public URLs — `BLOCKED`.

The briefs already list fixed constraints, exact unresolved decisions, expected
future zones and non-goals. Do not spend model budget rediscovering them.

## BE-006 boundary

Robokassa one-time manual purchases of `Plan` without recurring auto-debit.
Receipts handled by Robokassa (Робочеки СМЗ). Endpoints:
`POST /api/v1/subscriptions/payments/`, `POST/GET /api/v1/subscriptions/payments/robokassa/result/`,
UX landing `success/` and `fail/`. Idempotent ResultURL handler with `select_for_update()`.


## Token-saving execution rule

For the selected backend feature:

1. read only its feature brief and listed authoritative inputs;
2. confirm those facts against current `main`;
3. do not re-review shipped specs unrelated to the selected boundary;
4. for `READY_FOR_SPEC`, surface only the explicitly listed owner decisions;
5. for implementation-ready work, make a compact module/file zone plan rather
   than another architecture essay;
6. do not spawn routine architect/scout/security/self-review chains.

Normal implementation-ready flow:

`DESIGN(Grok) -> DESIGN_REVIEW(Gemini) -> IMPLEMENT(Grok) -> QUALITY_GATE -> FINAL_REVIEW(Gemini) -> PR`

## Deterministic quality gate

Run the same checks as GitHub CI before final Gemini review:

```text
uv run ruff format --check .
uv run ruff check .
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run pytest --create-db
```

If one command fails, Grok fixes the concrete failure and reruns only that
failed check. After convergence, run the full gate once for final evidence.

## Carry-forward constraints

- The two learning owner decisions remain unresolved:
  score threshold for automatic Topic completion and the long-term policy for
  exposing `correct_answer_ids` after submit. Do not silently close them.
- Paid content remains deny-by-default until BE-005 supplies the entitlement
  source.
- No concrete object-storage provider is selected.
- Capability paths for protected media must not be access-logged.
- Bulk/import, profile/preferences, slug URL migration and dashboard aggregates
  stay blocked until their roadmap brief says otherwise.
- Do not add Celery/Kafka/RabbitMQ without a concrete accepted use case.

## Source-of-truth pointers

- backend guardrails: `AGENTS.md`;
- accepted product decisions: sibling `../medcore-docs/decisions/`;
- shipped implementation contracts: `specs/`;
- backend architecture: `docs/architecture/`;
- not-yet-specified roadmap: `backend-features/`.
