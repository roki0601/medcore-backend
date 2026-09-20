# Feature 005 — Subscription core and paid entitlement

- Status: PROPOSED_BLOCKED_FOR_OWNER_DECISION
- Date: 2026-09-20
- Owning Django app: `apps.subscriptions`
- Consumers: `apps.content`, `apps.learning`, `apps.media`, frontend web client

> [!WARNING]
> This specification is NOT approved for production merge. Implementation is
> blocked pending explicit owner resolution of decision packet D1–D8.
> No accepted decision record currently exists in `medcore-docs` or `.omp/decisions/`.

## 1. Summary and Context

MedCore content uses the `demo | free | paid` access model (ADR 0007). Currently,
the access seam `apps.subscriptions.policy.has_paid_content_entitlement(user)`
returns `False` for all callers, keeping `paid` topics, media and learning workflows
deny-by-default.

Feature 005 addresses the subscription core and entitlement source behind this seam.
However, before code can be accepted and merged, the owner must make explicit choices
on decisions D1–D8 described in `backend-features/BE-005-subscriptions-core.md`.

---

## 2. Owner Decision Packet D1–D8 (Pending Owner Resolution)

### D1. Subscription statuses and state transitions

- **Options**:
  - *Option A (Derived + 3 stored statuses)*: Stored statuses `ACTIVE`, `CANCELLED`, `EXPIRED`. Entitlement is active if `status in (ACTIVE, CANCELLED)` and `starts_at <= now < expires_at`. If `now >= expires_at`, access is denied regardless of stored status (resilient to cron lag).
  - *Option B (Strict stored state)*: Entitlement relies purely on `status == ACTIVE`. A background job must immediately transition subscriptions to `EXPIRED` at `expires_at`.
  - *Option C (Extended statuses)*: Add `PAST_DUE`, `GRACE_PERIOD`, `TRIALING` statuses in addition to `ACTIVE`, `CANCELLED`, `EXPIRED`.
- **Model / API Impact**:
  - Option A requires check constraint `status in ('active', 'cancelled', 'expired')` and timestamp-based selector filtering.
  - Option B requires periodic celery/cron worker (forbidden in MVP without decision).
  - Option C expands choices and requires mapping each state to an entitlement boolean.
- **Pros & Risks**:
  - Option A: + Simple, zero worker dependency, reliable against clock drift; - status in DB might stay `active` after expiry until an update or manual sweep.
  - Option B: + Explicit DB state; - dangerous without async workers: users might retain access if worker fails.
  - Option C: + Granular; - unnecessary complexity for MVP before payment integration.
- **Agent Recommendation (NOT accepted decision)**: Option A.

---

### D2. Plan → Entitlement mapping

- **Options**:
  - *Option A (Universal paid access)*: Any active plan grants universal entitlement to all `paid` topics. Single boolean policy `has_paid_content_entitlement(user)`.
  - *Option B (Named capabilities/scopes)*: Plans grant capabilities (e.g. `access_cardiology`, `access_surgery`), and Topic requires specific capability.
  - *Option C (Per-topic ACL)*: User/Plan maps to individual topics.
- **Model / API Impact**:
  - Option A: No extra tables or relations. Policy checks existence of unexpired subscription.
  - Option B: Requires `Capability` model, M2M between `Plan` and `Capability`, and `Topic.required_capability`.
  - Option C: Forbidden by `AGENTS.md` and MVP principles.
- **Pros & Risks**:
  - Option A: + Fits ADR 0007 completely, zero join overhead; - cannot sell individual subjects separately.
  - Option B: + Future flexibility; - violates YAGNI for current single-catalog MVP.
- **Agent Recommendation (NOT accepted decision)**: Option A for MVP.

---

### D3. Concurrent and overlapping subscriptions

- **Options**:
  - *Option A (Extend on renewal, single unexpired row enforced in service)*: A user should have at most one active/unexpired subscription at any time. Extension moves `expires_at`.
  - *Option B (DB-level exclusion / partial unique index)*: Enforce `UniqueConstraint` on `(user)` where `status == 'active'` or PostgreSQL range exclusion constraint (`tsrange`).
  - *Option C (Allow stacking/overlapping rows)*: Allow multiple concurrent subscription rows; user is entitled if *at least one* is valid at `now`.
- **Model / API Impact**:
  - Option A: Requires transactional service checks on creation/extension.
  - Option B: Strict DB constraint. Requires PostgreSQL btree_gist extension for timestamp overlap checks, or partial unique constraint on active status.
  - Option C: Permissive DB schema, policy uses `.filter(...).exists()`.
- **Pros & Risks**:
  - Option A: + Flexible for manual admin extension; - does not prevent race conditions if concurrent writes occur.
  - Option B: + Concurrency-safe; - complex migration/extension dependencies in Postgres.
  - Option C: + Simple writes; - ambiguous accounting if user buys two plans concurrently.
- **Agent Recommendation (NOT accepted decision)**: Option A with service-level validation in MVP, transitioning to B once payment webhooks are implemented.

---

### D4. Trial semantics

- **Options**:
  - *Option A (Schema-ready only)*: `Plan.is_trial` and `Subscription.is_trial` boolean flags exist. Manual admin assignment only; no automated user endpoint in MVP.
  - *Option B (Automated self-service trial)*: Endpoint `POST /api/v1/subscriptions/trial/` granting one-time 7-day trial per user (tracked via `User.trial_used_at`).
  - *Option C (No trial in schema)*: Omit trial concepts completely until BE-006.
- **Model / API Impact**:
  - Option A: Simple boolean fields on Plan/Subscription.
  - Option B: Extra user tracking field, new mutation endpoint, abuse prevention logic.
  - Option C: Zero trial fields.
- **Pros & Risks**:
  - Option A: + Meets "architecture must allow trial" constraint without adding complex abuse-vector logic before auth/phone verification.
  - Option B: + Ready for product trials; - risk of sybil abuse (creating unlimited Telegram accounts if free).
- **Agent Recommendation (NOT accepted decision)**: Option A.

---

### D5. Cancellation and expiry semantics

- **Options**:
  - *Option A (Cancel-at-period-end)*: Cancelling marks `status = CANCELLED`, user retains access until `expires_at`.
  - *Option B (Cancel-now / revoke immediately)*: Cancelling sets `status = CANCELLED` and `expires_at = now`, revoking entitlement immediately.
  - *Option C (Deferred cancellation)*: User sets `cancel_at_period_end = True`, row stays `ACTIVE` until cron worker expires it.
- **Model / API Impact**:
  - Option A: Policy checks `status in ('active', 'cancelled')` and `now < expires_at`.
  - Option B: Immediate loss of access.
  - Option C: Additional boolean field on model.
- **Pros & Risks**:
  - Option A: + Standard SaaS practice, respects paid period; - requires frontend to explain "access active until X".
  - Option B: + Immediate effect; - unfair to users who paid for the full period.
- **Agent Recommendation (NOT accepted decision)**: Option A.

---

### D6. Account deletion and retention

- **Options**:
  - *Option A (CASCADE delete with User)*: Subscriptions are deleted when the `User` is deleted.
  - *Option B (SET_NULL / Anonymize)*: `Subscription.user` is nullable on delete to preserve financial accounting.
  - *Option C (Separate immutable Audit table)*: `Subscription` cascades, but payment records (in BE-006) are immutable and retained.
- **Model / API Impact**:
  - Option A: `ForeignKey(User, on_delete=CASCADE)`.
  - Option B: `ForeignKey(User, null=True, on_delete=SET_NULL)`.
  - Option C: `CASCADE` on Subscription; payments app in BE-006 owns financial records.
- **Pros & Risks**:
  - Option A: + Simple, consistent with `apps.learning` and GDPR/data-protection erasure; - subscription history lost upon deletion.
  - Option C: + Clean boundary separation: access entitlement cascades, legal financial receipts stay in payments domain.
- **Agent Recommendation (NOT accepted decision)**: Option A for `apps.subscriptions` in MVP, leaving financial retention to BE-006.

---

### D7. User-facing API endpoints

- **Options**:
  - *Option A (Read-only minimal)*:
    - `GET /api/v1/subscriptions/plans/` (public);
    - `GET /api/v1/subscriptions/current/` (authenticated).
  - *Option B (Read-only + history)*: Add `GET /api/v1/subscriptions/history/`.
  - *Option C (Include mutations)*: Include cancel endpoint before payment provider.
- **Model / API Impact**:
  - Option A: 2 lightweight read views, serializers, throttled.
  - Option B/C: Additional views and mutation logic.
- **Pros & Risks**:
  - Option A: + Minimal surface area, gives frontend exactly what is needed to render pricing and account status; - no self-service cancellation yet.
- **Agent Recommendation (NOT accepted decision)**: Option A.

---

### D8. Manual / Admin provisioning

- **Options**:
  - *Option A (Enabled)*: Register `Plan` and `Subscription` in Django Admin for staff/curator creation and extension.
  - *Option B (Disabled / Read-only)*: Admin is read-only; provisioning must happen via management command or payment webhooks.
- **Model / API Impact**:
  - Option A: Full `ModelAdmin` in `apps.subscriptions.admin`.
  - Option B: Read-only `ModelAdmin`.
- **Pros & Risks**:
  - Option A: + Allows testing, manual grants to beta users and QA without fake payment provider; - risk of human error during manual edits.
- **Agent Recommendation (NOT accepted decision)**: Option A.

---

## 3. Known Discrepancy in Proposed Implementation

### D3 Concurrency Enforcement Discrepancy
While recommendation D3 suggests that a user should hold at most one active/unexpired subscription at a time:
- The database schema in `apps/subscriptions/models.py` currently has an index `(user, status, expires_at)` but does **NOT** enforce a uniqueness or exclusion constraint across overlapping time intervals.
- Multiple active rows for a single user are technically allowed by the table structure.
- Until the owner explicitly chooses between Option A (service-level check), Option B (DB exclusion constraint), or Option C (allow overlapping rows), no arbitrary constraint is forced into the migration.

### `auto_renew` Scope Creep Removed
- The field `auto_renew` was previously included in the prototype. It has been removed from the model, admin, serializer, and migration to avoid unauthorized product/contract additions prior to BE-006.

---

## 4. Architecture Guardrails and Fixed Constraints

- `premium` is not a User role;
- Topic access levels remain strictly `demo | free | paid`;
- `content`, `learning`, and `media` never inspect `Subscription` fields directly;
  they query only `apps.subscriptions.policy.has_paid_content_entitlement(user)`;
- Editor/Admin roles do NOT bypass paid entitlement in user-facing APIs;
- Payment gateways (YooKassa, Robokassa, Stripe, etc.) are NOT implemented in BE-005;
- Celery, Redis queuing, and webhook processing are out of scope for BE-005.
