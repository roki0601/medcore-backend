# BE-006 — Payment provider integration

Status: BLOCKED

## Goal

Connect the accepted subscription domain to one concrete payment provider
without leaking provider-specific semantics into `content` or `learning`.

## Start conditions

Do not spec or implement this until all are true:

1. BE-005 subscription state/entitlement contract is approved and implemented;
2. owner selects the concrete payment provider;
3. required fiscal receipt behavior for the owner's operating model is known;
4. provider webhook verification/idempotency requirements are available from
   official provider documentation.

## Fixed boundaries

When this feature becomes active:

- provider code belongs under `subscriptions` adapter/integration modules;
- content/media/learning continue to ask only
  `has_paid_content_entitlement(user)`;
- card/payment credentials are never stored by MedCore unless the chosen
  provider contract explicitly requires safe tokens;
- webhook authenticity must be verified;
- webhook processing must be idempotent;
- provider event IDs or another stable idempotency key must prevent duplicate
  subscription transitions;
- raw secrets/payment payloads must not be logged;
- payment success from frontend is not authoritative; backend/provider event is;
- retries must not create duplicate subscriptions or extend twice;
- no Celery is added automatically. Use synchronous handling unless a concrete
  provider/runtime requirement proves a worker is needed.

## Owner decisions still required

At activation time record:

- provider name;
- one-time payment vs recurring provider subscription mechanics;
- purchase/create-payment endpoint contract;
- redirect/return/cancel URL behavior;
- webhook event→Subscription transition mapping;
- refund/chargeback behavior;
- fiscal receipt responsibility;
- retry and reconciliation strategy.

## Expected future zones

After the above is fixed:

- provider client/adapter;
- payment intent/session service;
- webhook endpoint + signature verification;
- idempotency persistence;
- subscription transition integration;
- API/OpenAPI/tests.

Do not pre-create provider-agnostic abstractions with no chosen provider.
