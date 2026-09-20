# BE-006 — Payment provider integration

Status: MERGED (PR #14)

## Goal

Connect the accepted subscription domain to one concrete payment provider
without leaking provider-specific semantics into `content` or `learning`.

## Implemented architecture

1. **Provider**: Robokassa.
2. **Payment mechanics**: One-time manual period purchases of `Plan` (no recurring auto-debit).
3. **Receipt / Fiscalization**: Робочеки СМЗ (handled by Robokassa; no direct backend FNS integration).
4. **Endpoints**:
   - `POST /api/v1/subscriptions/payments/`
   - `POST` / `GET` `/api/v1/subscriptions/payments/robokassa/result/`
   - `GET /api/v1/subscriptions/payments/robokassa/success/`
   - `GET /api/v1/subscriptions/payments/robokassa/fail/`
5. **Persistence**: `Payment` model with `user`, `plan`, `subscription`, `amount`, `status`, `provider`.
6. **Concurrency & Idempotency**: `transaction.atomic()` with `select_for_update()`, duplicate callbacks return `OK{InvId}` safely.


## Expected future zones

After the above is fixed:

- provider client/adapter;
- payment intent/session service;
- webhook endpoint + signature verification;
- idempotency persistence;
- subscription transition integration;
- API/OpenAPI/tests.

Do not pre-create provider-agnostic abstractions with no chosen provider.
