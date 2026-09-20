# Feature 006 — Payment provider integration (Robokassa)

- Status: ACCEPTED
- Provider: ROBOKASSA
- Date: 2026-09-20
- Owning Django app: `apps.subscriptions`
- Consumers: authenticated users, Robokassa payment gateway

## 1. Summary and Business Goal

MedCore connects the accepted subscription domain (BE-005, ADR 0009) to a concrete payment provider to enable users to purchase subscription plans.
The chosen provider is **Robokassa** for one-time manual period purchases of `Plan` (no recurring auto-debit, no stored card credentials).
Fiscalization follows the **Робочеки СМЗ** model (self-employed + "Мой налог"), where receipt generation and fiscal reporting are delegated to Robokassa.

## 2. Architecture and Boundaries

1. **Provider Isolation**:
   - Robokassa-specific integration logic is encapsulated in `apps.subscriptions.robokassa`.
   - Content, learning, and media apps remain agnostic of payment processing and continue relying solely on `has_paid_content_entitlement(user)`.
2. **Persistence (`Payment` model and retention)**:
   - `id`: BigAutoField, passed as internal invoice ID `InvId` to Robokassa.
   - `user`: ForeignKey to `User` (`null=True, blank=True, on_delete=models.SET_NULL`).
     Financial audit retention: deleting a user account retains the payment history (InvId, plan, amount, provider, status, paid_at) while nullifying the personal user reference.
     `Subscription.user` remains `CASCADE` per ADR 0009.
   - `plan`: ForeignKey to `Plan` with `PROTECT` on deletion.
   - `subscription`: OneToOneField to `Subscription` (`SET_NULL`, nullable until payment succeeds).
   - `amount`: Snapshot of `Plan.price_rub` at payment creation time.
   - `status`: `pending` -> `succeeded` | `failed`.
   - `provider`: `robokassa`.
   - `paid_at`: timestamp set on successful callback.
3. **Fail-Closed Security & Algorithm Validation**:
   - System check (`subscriptions.E001`, `subscriptions.E002`) validates configuration in production (`DEBUG=False`).
   - Payment initialization fails closed (raises `RobokassaConfigurationError` -> 503) if merchant login, Password #1, or hash algorithm are invalid/missing.
   - ResultURL callback fails closed (`verify_result_signature` returns `False`) if Password #2 is empty, preventing forged callbacks against unconfigured servers.
   - Hash algorithm is strictly validated against supported algorithms (`sha256`, `md5`) and MUST match the algorithm selected in technical settings of the Robokassa Merchant Cabinet.
   - Credentials, passwords, and tokens are never logged.
4. **Receipt and Fiscalization**:
   - Robokassa cabinet is configured with "Робочеки СМЗ".
   - Backend does not connect directly to FNS ("Мой налог"). If user email is present, it is forwarded in checkout parameters (`Email`); otherwise, Robokassa collects it at checkout.
5. **Idempotency and Concurrency**:
   - ResultURL handler executes within `transaction.atomic()` using `select_for_update()` on the `Payment` record.
   - Duplicate callbacks for already succeeded payments return `OK{InvId}` without creating extra subscriptions.

## 3. API Contract

### 3.1. Initialize Payment
- `POST /api/v1/subscriptions/payments/`
- Permission: `IsAuthenticated`
- Request: `{"plan_id": <int>}`
- Response (201 Created):
  ```json
  {
    "payment_id": 42,
    "payment_url": "https://auth.robokassa.ru/Merchant/Index.aspx?MerchantLogin=...&OutSum=990.00&InvId=42&Description=...&SignatureValue=...&IsTest=1",
    "amount": "990.00",
    "status": "pending"
  }
  ```

### 3.2. Robokassa ResultURL Webhook Callback
- `POST` / `GET` `/api/v1/subscriptions/payments/robokassa/result/`
- Permission: `AllowAny`
- Parameters: `OutSum`, `InvId`, `SignatureValue`
- Signature verification:
  - Calculated using Password #2: `hashlib.sha256(f"{OutSum}:{InvId}:{Password_2}".encode("utf-8")).hexdigest()`.
  - Constant-time comparison `hmac.compare_digest`.
- Result:
  - Success (200 OK): plaintext body `OK{InvId}`.
  - Failure (400 Bad Request): plaintext error description (e.g. `bad request: bad signature`, `bad request: amount mismatch`).

### 3.3. UX Landing Pages
- `GET /api/v1/subscriptions/payments/robokassa/success/` -> `{"status": "success", "message": "Оплата успешно завершена."}`
- `GET /api/v1/subscriptions/payments/robokassa/fail/` -> `{"status": "failed", "message": "Оплата отменена или не удалась."}`
