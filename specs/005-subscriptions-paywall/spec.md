# Feature 005 — Subscription core and paid entitlement

- Status: APPROVED
- Date: 2026-09-20
- Owning Django app: `apps.subscriptions`
- Consumers: `apps.content`, `apps.learning`, `apps.media`, frontend web client

## 1. Summary and Business Goal

MedCore content uses the `demo | free | paid` access model (ADR 0007). Currently,
the access seam `apps.subscriptions.policy.has_paid_content_entitlement(user)`
always returns `False`, leaving all `paid` topics, media and learning workflows
deny-by-default.

Feature 005 implements the foundational subscription and entitlement domain:
1. `Plan` and `Subscription` models with start/expiry timestamps and statuses;
2. Real entitlement resolution in `apps.subscriptions.policy.has_paid_content_entitlement`;
3. Read-only user-facing endpoints for available plans and current subscription status;
4. Django Admin integration for manual creation and extension of subscriptions before payment provider integration (BE-006).

## 2. Resolved Owner Decisions (D1–D8)

As required by `backend-features/BE-005-subscriptions-core.md`, the following
decisions are explicitly accepted:

### D1. Subscription statuses
- Stored statuses:
  - `ACTIVE = "active"`
  - `CANCELLED = "cancelled"`
  - `EXPIRED = "expired"`
- Entitlement rule:
  A user has active entitlement if there exists at least one subscription where:
  - `status in ("active", "cancelled")` AND
  - `starts_at <= now < expires_at`.
- Even if a subscription was cancelled (`CANCELLED`), access is maintained
  until the end of the already paid period (`expires_at`), following the
  standard cancel-at-period-end rule.
- If `now >= expires_at`, entitlement is `False` regardless of the stored status.
  (Runtime policy calculates entitlement dynamically from timestamps).

### D2. Plan → Entitlement mapping
- In MVP, every active `Plan` grants universal access to all `paid` topics.
- No per-topic ACL or complex capability matrix is introduced at this stage.

### D3. Concurrent/overlapping subscriptions
- At any point in time, a user should have at most one active/unexpired
  subscription.
- Renewal extends the subscription period (`expires_at`) or replaces it cleanly.
- If multiple unexpired subscriptions exist due to legacy data, entitlement is
  granted if *any* unexpired subscription is active or cancelled-within-period.

### D4. Trial
- Schema-ready: `Plan.is_trial` and `Subscription.is_trial` boolean flags exist.
- In MVP, trial subscriptions can be manually assigned in Django Admin.
- Self-service automated trial provisioning is deferred to BE-006 / payment integration.

### D5. Cancellation and expiry
- Cancel-at-period-end: cancelling a subscription marks `status = CANCELLED`.
- The user retains entitlement until `expires_at`.
- Access is denied when `now >= expires_at`.

### D6. Account deletion and retention
- `Subscription.user` uses `on_delete=models.CASCADE`.
- When a user deletes their account, subscription rows are deleted with the user.
- Financial audit logs and payment provider transactions will be handled
  separately in BE-006 with appropriate retention policies.

### D7. User-facing API
- Two read-only endpoints:
  - `GET /api/v1/subscriptions/plans/` (public): list of available active plans.
  - `GET /api/v1/subscriptions/current/` (authenticated): current user's entitlement
    status (`has_access: bool`) and current active subscription details (or `null`).

### D8. Manual / Admin provisioning
- `Plan` and `Subscription` are fully registered in Django Admin (`apps.subscriptions.admin`),
  enabling administrators and support staff to create, modify, and extend subscriptions.

## 3. Architecture Guardrails and Fixed Constraints

- `premium` is not a User role;
- Topic access levels remain strictly `demo | free | paid`;
- `content`, `learning`, and `media` never inspect `Subscription` fields directly;
  they query only `apps.subscriptions.policy.has_paid_content_entitlement(user)`;
- Editor/Admin roles do NOT bypass paid entitlement in user-facing APIs;
- Payment gateways (YooKassa, Robokassa, Stripe, etc.) are NOT implemented in BE-005;
- Celery, Redis queuing, and webhook processing are out of scope for BE-005.
