# Feature 005 — Implementation Plan

## Zones

### Z0 — Domain & Migrations
- Define `Plan` and `Subscription` in `apps/subscriptions/models.py`.
- Enforce constraints:
  - `status in ("active", "cancelled", "expired")`
  - `expires_at > starts_at`
  - `duration_days > 0`
  - `price_rub >= 0`
- Generate and run migrations `0002_initial_plans_and_subscriptions.py`.
- Register models in `apps/subscriptions/admin.py` with custom ModelAdmins for management.

### Z1 — Entitlement Policy & Selectors
- Implement `apps/subscriptions/selectors.py`:
  - `get_active_subscription(user)`
  - `list_active_plans()`
- Connect real logic in `apps/subscriptions/policy.py`:
  - `has_paid_content_entitlement(user)`: returns `True` if authenticated, active user has an unexpired active or cancelled-within-period subscription.
- Thorough unit tests for all timestamp/status edge cases in `apps/subscriptions/tests/test_policy.py`.

### Z2 — Subscriptions API
- Create serializers in `apps/subscriptions/serializers.py`:
  - `PlanSerializer`
  - `CurrentSubscriptionResponseSerializer`
- Implement views in `apps/subscriptions/views.py`:
  - `PlanListView` (`GET /api/v1/subscriptions/plans/`)
  - `CurrentSubscriptionView` (`GET /api/v1/subscriptions/current/`)
- Configure routing in `apps/subscriptions/urls.py` and `config/urls.py`.
- Annotate with `drf-spectacular` `@extend_schema`.
- Write API tests in `apps/subscriptions/tests/test_api.py`.

### Z3 — Cross-domain Integration & Verification
- Test that an authenticated user with an active subscription can read paid topics in `apps/content` without monkeypatching.
- Test that a user with an expired subscription or no subscription receives `403 TOPIC_ENTITLEMENT_REQUIRED`.
- Verify full project quality gate: ruff, migrations check, manage.py check, pytest.
