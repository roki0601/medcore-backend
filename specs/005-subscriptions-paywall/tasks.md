# Feature 005 — Tasks

## Tasks

- [x] T001: Define `Plan` and `Subscription` models in `apps/subscriptions/models.py` with valid choices, constraints, and string representations.
- [x] T002: Generate and apply migration for `apps.subscriptions`.
- [x] T003: Register `Plan` and `Subscription` in `apps/subscriptions/admin.py` with helpful list display, filters, and search.
- [x] T004: Implement `apps/subscriptions/selectors.py` and connect `apps/subscriptions/policy.py`.
- [x] T005: Expand `apps/subscriptions/tests/test_policy.py` with boundary timestamp and status matrix tests.
- [x] T006: Implement serializers, views, and URL configuration for `GET /api/v1/subscriptions/plans/` and `GET /api/v1/subscriptions/current/`.
- [x] T007: Register `apps.subscriptions.urls` in `config/urls.py` and document with `drf-spectacular`.
- [x] T008: Add API tests in `apps/subscriptions/tests/test_api.py`.
- [x] T009: Add cross-domain integration tests in `apps/content/tests/test_access.py` / `test_api.py` confirming live entitlement resolution on paid topics.
- [x] T010: Run complete deterministic quality gate (Ruff, Django checks, pytest).
- [x] T011: Update `PROJECT_STATE.md` and `memory.md`.
