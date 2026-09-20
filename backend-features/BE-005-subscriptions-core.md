# BE-005 — Subscription core and paid entitlement

Status: READY_FOR_SPEC  
Implementation status: BLOCKED until the owner decisions below are resolved.

## Goal

Implement the `subscriptions` domain so an authenticated user with a valid
subscription/entitlement can read `paid` Topic content, media and learning
resources through the already-existing policy seam:

`apps.subscriptions.policy.has_paid_content_entitlement(user)`.

This feature must not redesign content or learning access. It supplies the
missing entitlement source behind their existing contracts.

## Authoritative inputs

Read only:

- `AGENTS.md`;
- `PROJECT_STATE.md`;
- this file;
- `../medcore-docs/decisions/0004-mvp-decision-register.md`, items 12–15,
  115–119, 133–134;
- `../medcore-docs/decisions/0007-content-access-model.md`;
- `../medcore-docs/decisions/0008-mvp-auth-content-and-integration-contract.md`;
- `docs/architecture/auth-and-access.md`;
- `docs/architecture/domain-model.md`;
- `docs/architecture/open-questions.md`;
- `apps/subscriptions/policy.py`;
- existing access call sites in `content`, `media`, and `learning`.

Do not reread old prototype/frontend files. They are not the backend
subscription contract.

## Already fixed — do not debate again

The spec must preserve all of these:

- `premium` is not a User role;
- owning app is `subscriptions`;
- Topic is the main paid-content boundary;
- access levels stay exactly `demo | free | paid`;
- `demo`: anonymous allowed;
- `free`: authentication required, no subscription required;
- `paid`: authentication + active entitlement required;
- editor/admin role alone does **not** bypass paid entitlement in user-facing
  APIs;
- content and learning do not inspect Subscription fields directly;
- all paid access goes through `subscriptions.policy`;
- multiple plans/tariffs must be structurally possible;
- `Subscription` belongs to User and Plan;
- `starts_at` and `expires_at` are required product concepts;
- architecture must allow trial later;
- payment provider remains a separate boundary and is not selected here;
- frontend visibility is never the security boundary;
- no arbitrary user→topic ACL is introduced;
- no independent paid flags are added to ContentBlock/Flashcard/Quiz;
- User deletion must not leave user-owned subscription state orphaned.

## Current runtime seam

Today:

```python
has_paid_content_entitlement(user) -> False
```

Content/media/learning already call this seam. The subscription feature should
replace the implementation behind that seam without changing their public
access-level contract.

Before planning new call sites, search current `main`; do not duplicate policy
checks that already exist.

## Owner decisions required before implementation

Do **not** let an agent choose these by taste. The spec review should surface
this exact compact packet and wait for an accepted decision.

### D1. Subscription statuses

Define the exact stored state set and transitions.

Need explicit answer for:

- which statuses exist;
- which statuses grant entitlement;
- whether expiry is stored as a status, derived from `expires_at`, or both;
- whether cancellation is immediate or end-of-period.

### D2. Plan → entitlement mapping

Choose one MVP rule:

- every active plan grants all `paid` Topics; or
- Plans grant named entitlement/capability codes and `paid` content checks one
  required capability.

Do not create per-topic subscription ACL unless explicitly accepted.

### D3. Concurrent/overlapping subscriptions

Define:

- may one User have more than one entitlement-granting Subscription at once;
- renewal creates a new row or extends/replaces an existing row;
- how overlapping periods behave.

### D4. Trial

Decide MVP behavior:

- trial implemented now or only schema-ready;
- if implemented: eligibility, one-time rule, start/end timestamps and whether
  trial grants the same paid entitlement.

### D5. Cancellation/expiry

Define:

- cancel-now vs cancel-at-period-end;
- whether a cancelled-but-not-expired row still grants access;
- what timestamp/state marks entitlement loss.

### D6. Account deletion and retention

Define whether Subscription rows:

- cascade-delete with User; or
- retain provider/audit metadata after user deletion in a de-identified form.

Current user-owned learning state already cascades; do not assume the same legal
retention rule for payment metadata without a decision.

### D7. User-facing API

Define the minimum endpoints frontend actually needs, for example only after
acceptance:

- available plans;
- current subscription/entitlement.

Do not invent purchase/cancel endpoints until payment/cancel semantics are
accepted.

### D8. Manual/admin provisioning

Decide whether MVP may create/extend subscriptions manually in Django Admin
before a payment provider ships.

This is useful for development but is still a product/operations decision, not
an implicit coding shortcut.

## Spec shape after decisions are resolved

Once D1–D8 are accepted, create `specs/005-subscriptions-paywall/` with:

- `spec.md`;
- `data-model.md`;
- `contracts/subscriptions-api.md`;
- `plan.md`;
- `tasks.md`;
- implementation-readiness checklist.

Do not create placeholder migrations/code before the contract is accepted.

## Expected implementation zones after approval

This is guidance so PLAN stays short.

### Z0 — domain/migrations

Likely:

- `apps/subscriptions/models.py`;
- migrations;
- admin registration if accepted.

Own Plan/Subscription constraints, indexes and time/state invariants here.

### Z1 — entitlement policy

Likely:

- `apps/subscriptions/policy.py`;
- selectors/services if needed;
- policy tests.

The public seam should remain small. Content/learning/media must not know model
internals.

### Z2 — subscriptions API

Only the endpoints accepted in D7.

Use existing API error envelope, auth, throttling and OpenAPI conventions.

### Z3 — cross-domain regression

Prove existing `paid` access changes from deny→allow only when entitlement is
valid, without changing `demo/free` semantics.

Prefer tests at the policy/access boundary rather than duplicating the same
matrix in every app.

## Minimum implementation tests after approval

Do not write these until the spec is accepted.

Must cover:

- no entitlement → paid denied;
- valid entitlement → paid allowed;
- inactive/expired/cancelled state according to accepted D1/D5;
- demo/free behavior unchanged;
- editor/admin role alone does not bypass entitlement;
- boundary timestamps at `starts_at`/`expires_at`;
- User deletion/retention according to D6;
- concurrency/unique constraints implied by D3;
- OpenAPI for any new user-facing endpoints.

Avoid a giant cross-product across content/media/learning when one policy test
plus a few integration regressions proves the same contract.

## Explicit non-goals

Do not implement in BE-005 unless separately accepted:

- Robokassa/YooKassa/Stripe/provider SDK;
- provider webhooks;
- receipt/fiscalization logic;
- invoices;
- promo codes;
- refunds;
- arbitrary per-topic ACL;
- analytics;
- email notifications;
- Celery;
- frontend pricing UI;
- automatic trial assumptions.

## Exit condition

BE-005 becomes `READY_FOR_IMPLEMENTATION` only when D1–D8 are recorded in an
accepted decision/spec and Gemini spec review has no unresolved BLOCKER/HIGH.
