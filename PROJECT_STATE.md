# MedCore backend OMP project state

This file tracks the project-local backend workflow. It is not a replacement for
accepted product decisions, approved specs, architecture documents or
`AGENTS.md`.

## Current state

- Stage: `VERIFIED`.
- Active implementation feature: `005-subscriptions-paywall` (PR created, ready for review).
- Shipped backend feature specs:
  - `001-telegram-auth-account` — merged;
  - `002-content-catalog-access` — merged;
  - `004-content-api-media` — merged;
  - `003-learning-state` — merged;
  - OpenAPI/runtime contract follow-up — merged.
- Next pending merge: `005-subscriptions-paywall` (spec in `specs/005-subscriptions-paywall/`).
- Later roadmap items BE-006–BE-010 are explicitly BLOCKED until their listed
  owner/upstream decisions exist.
- Human review and merge remain required.

## Current validated baseline

Backend 003 learning state and the OpenAPI follow-up are already merged. The
baseline includes:

- Telegram-only auth/session contract;
- catalog + Topic `demo/free/paid` access model;
- synchronous content CRUD/integration contract;
- protected media boundary;
- topic/theory progress;
- flashcard review API;
- resumable quiz attempts and scoring;
- OpenAPI coverage for shipped routes.

Do not reopen these contracts merely because the next feature touches the same
apps.

## Backend roadmap

Use `backend-features/README.md` as the executable queue for work that does not
yet have an approved spec.

Order:

1. BE-005 — subscription core and paid entitlement — `READY_FOR_SPEC`;
2. BE-006 — payment provider integration — `BLOCKED`;
3. BE-007 — dashboard/progress aggregate API — `BLOCKED`;
4. BE-008 — profile/study preferences — `BLOCKED`;
5. BE-009 — content bulk/import extensions — `BLOCKED`;
6. BE-010 — slug-based public URLs — `BLOCKED`.

The briefs already list fixed constraints, exact unresolved decisions, expected
future zones and non-goals. Do not spend model budget rediscovering them.

## BE-005 boundary

The next feature is subscriptions/paywall, but only its **spec** may advance.

Already accepted:

- `premium` is not a role;
- Topic access remains `demo | free | paid`;
- paid access requires authentication + active entitlement;
- content/media/learning ask only
  `apps.subscriptions.policy.has_paid_content_entitlement(user)`;
- editor/admin role alone does not bypass paid access;
- Plan/Subscription belong to `subscriptions`;
- multiple plans must be possible;
- `starts_at` and `expires_at` are required concepts;
- architecture must allow trial;
- payment provider remains separate/TBD.

Implementation remains blocked until the exact decision packet D1–D8 in
`backend-features/BE-005-subscriptions-core.md` is accepted.

Do not create subscription migrations/models/API by guessing those decisions.

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
