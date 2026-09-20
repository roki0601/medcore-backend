# Feature 005 — Tasks

Source of truth: `medcore-docs/decisions/0009-subscriptions-core-and-paid-entitlement.md` (ADR 0009)

## Tasks

- [x] T001: Record owner decisions D1–D8 in `medcore-docs/decisions/0009-subscriptions-core-and-paid-entitlement.md`.
- [x] T002: Define `Plan` and `Subscription` models in `apps/subscriptions/models.py` adhering to ADR 0009 (statuses `ACTIVE`/`CANCELLED`, no persisted `EXPIRED`, no `is_trial`, support overlapping subscriptions).
- [x] T003: Generate and verify migration `apps/subscriptions/migrations/0001_initial.py`.
- [x] T004: Register `Plan` and `Subscription` in `apps/subscriptions/admin.py` for manual staff management (D8).
- [x] T005: Implement `apps/subscriptions/selectors.py` (`get_active_subscription` selecting latest `expires_at`, tie-breaking on newest `id`) and `apps/subscriptions/policy.py`.
- [x] T006: Comprehensive unit tests in `apps/subscriptions/tests/test_policy.py` covering boundary timestamps, cancel-at-period-end, and multiple overlapping subscriptions (D3).
- [x] T007: Implement serializers, views, and routing for `GET /api/v1/subscriptions/plans/` and `GET /api/v1/subscriptions/current/`.
- [x] T008: Register URLs in `config/urls.py` and document with `drf-spectacular`.
- [x] T009: API tests in `apps/subscriptions/tests/test_api.py` including overlapping subscription resolution.
- [x] T010: Cross-domain integration tests in `apps/content/tests/test_access.py` / `test_api.py` confirming live entitlement resolution on paid topics.
- [x] T011: Run complete deterministic quality gate (Ruff, Django checks, pytest --create-db).
- [x] T012: Update `PROJECT_STATE.md`.
