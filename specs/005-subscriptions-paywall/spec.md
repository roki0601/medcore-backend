# Feature 005 — Subscription core and paid entitlement

- Status: ACCEPTED
- Source of truth: `medcore-docs/decisions/0009-subscriptions-core-and-paid-entitlement.md` (ADR 0009)
- Date: 2026-09-20
- Owning Django app: `apps.subscriptions`
- Consumers: `apps.content`, `apps.learning`, `apps.media`, frontend web client

## 1. Summary and Business Goal

MedCore content uses the `demo | free | paid` access model (ADR 0007).
Feature 005 implements the foundational subscription and entitlement domain behind
the access seam `apps.subscriptions.policy.has_paid_content_entitlement(user)`.

Authoritative owner decisions D1–D8 were formally resolved and accepted in ADR 0009.

## 2. Accepted Decisions (ADR 0009)

### D1. Subscription status and expiry calculation
- Stored statuses: `ACTIVE` and `CANCELLED`.
- No separate persisted status `EXPIRED`. Expiry is dynamically calculated by time:
  `starts_at <= now < expires_at`.
- Entitlement is granted if:
  `status in (ACTIVE, CANCELLED)` and `starts_at <= now < expires_at`.
- After `now >= expires_at`, access is denied regardless of stored status.
- No Celery/cron background job is added to transition records to `expired`.
- `CANCELLED` follows cancel-at-period-end: cancelled subscription continues to grant access until `expires_at`.

### D2. Plan → Paid entitlement mapping
- Any active `Plan` grants universal entitlement to all `paid` topics.
- No capability codes, entitlement tables, per-topic ACL or independent paid flags on children.
- Content, learning, and media rely solely on `apps.subscriptions.policy.has_paid_content_entitlement(user)`.

### D3. Multiple and overlapping subscriptions
- A user may hold multiple `Subscription` rows, including overlapping time windows.
- No "one active subscription per user" limit and no PostgreSQL exclusion constraints.
- Entitlement is active if *at least one* subscription satisfies D1.
- If multiple subscriptions are concurrently valid, `get_active_subscription()` for `/current/` selects the record with the latest `expires_at`, and ties broken by newest `id` (`order_by("-expires_at", "-id")`).
- Renewal conceptually creates a new `Subscription` row.

### D4. Trial
- Trial is NOT implemented in BE-005.
- `Plan.is_trial`, `Subscription.is_trial`, `trial_used_at`, and trial endpoints are omitted.
- Architectural requirement: future trial additions (with BE-006) must not modify the base `demo/free/paid` access contract.

### D5. Cancellation
- Cancel-at-period-end: `CANCELLED` retains entitlement until `now >= expires_at`.
- No self-service user cancel endpoint in BE-005.

### D6. User deletion and retention
- `Subscription.user` uses `on_delete=models.CASCADE`.
- Future financial entities (payments, receipts, provider audit data in BE-006) are separate from `Subscription` and will follow separate retention policies.

### D7. User-facing API
- Exactly two endpoints:
  - `GET /api/v1/subscriptions/plans/` (public, `AllowAny`);
  - `GET /api/v1/subscriptions/current/` (authenticated, `IsAuthenticated`).
- Single evaluation of `get_active_subscription()` with single timestamp in `/current/`.

### D8. Django Admin
- Full manual management in Django Admin for `Plan` and `Subscription` (create, edit, change dates/status).
- Admin is an operations interface, not a policy bypass.

## 3. Architecture Guardrails

- `premium` is not a User role;
- Topic access levels remain strictly `demo | free | paid`;
- `content`, `learning`, and `media` never inspect `Subscription` fields directly;
  they query only `apps.subscriptions.policy.has_paid_content_entitlement(user)`;
- Editor/Admin roles do NOT bypass paid entitlement in user-facing APIs;
- Payment gateways (YooKassa, Robokassa, Stripe, etc.) are NOT implemented in BE-005;
- Celery, Redis queuing, and webhook processing are out of scope for BE-005.
