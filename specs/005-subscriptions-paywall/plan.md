# Feature 005 — Implementation Plan

Source of truth: `medcore-docs/decisions/0009-subscriptions-core-and-paid-entitlement.md` (ADR 0009)

## Zones

### Z0 — Domain & Migrations
- Define `Plan` and `Subscription` in `apps/subscriptions/models.py`.
- Enforce constraints:
  - `status in ("active", "cancelled")`
  - `expires_at > starts_at`
  - `duration_days > 0`
  - `price_rub >= 0`
- Migration `0001_initial.py` creates `Plan` and `Subscription`.
- Register models in `apps/subscriptions/admin.py` for manual staff management (D8).

### Z1 — Entitlement Policy & Selectors
- Implement `apps/subscriptions/selectors.py`:
  - `get_active_subscription(user)`: orders by `("-expires_at", "-id")` to deterministically pick latest expiration when multiple overlapping subscriptions exist (D3).
  - `list_active_plans()`: returns active plans ordered by `price_rub`, `duration_days`, `id`.
- Connect real logic in `apps/subscriptions/policy.py`:
  - `has_paid_content_entitlement(user)`: returns `True` if active/cancelled subscription is unexpired.
- Unit tests for all timestamp, cancel-at-period-end, and overlapping subscription cases in `apps/subscriptions/tests/test_policy.py`.

### Z2 — Subscriptions API
- Serializers in `apps/subscriptions/serializers.py`:
  - `PlanSerializer`
  - `CurrentSubscriptionResponseSerializer`
- Views in `apps/subscriptions/views.py`:
  - `PlanListView` (`GET /api/v1/subscriptions/plans/`)
  - `CurrentSubscriptionView` (`GET /api/v1/subscriptions/current/`)
- Configure routing in `apps/subscriptions/urls.py` and `config/urls.py`.
- API tests in `apps/subscriptions/tests/test_api.py`.

### Z3 — Cross-domain Integration & Verification
- Test that an authenticated user with an active subscription can read paid topics in `apps/content` without monkeypatching.
- Test that a user with an expired subscription or no subscription receives `403 TOPIC_ENTITLEMENT_REQUIRED`.
- Verify full project quality gate.
