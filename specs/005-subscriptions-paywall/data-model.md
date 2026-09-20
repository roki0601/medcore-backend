# Feature 005 — Data Model

Owning app: `apps.subscriptions`
Source of truth: `medcore-docs/decisions/0009-subscriptions-core-and-paid-entitlement.md` (ADR 0009)

## Entity Definitions

### `Plan`

Represents a commercial subscription tier/tariff offered to users.

| Field | Type | Attributes | Description |
|---|---|---|---|
| `id` | BigAutoField | Primary Key | Standard ID |
| `code` | SlugField | max_length=50, unique=True | Stable identifier (e.g. `monthly`, `yearly`) |
| `title` | CharField | max_length=255 | Public display title (e.g. "Месячная подписка") |
| `description` | TextField | blank=True, default="" | Human-readable details / marketing description |
| `price_rub` | DecimalField | max_digits=10, decimal_places=2 | Price in RUB |
| `duration_days` | PositiveIntegerField | > 0 | Duration of one subscription period in days |
| `is_active` | BooleanField | default=True, db_index=True | Whether plan is visible/available for purchase |
| `created_at` | DateTimeField | auto_now_add=True | UTC timestamp |
| `updated_at` | DateTimeField | auto_now=True | UTC timestamp |

Constraints:
- `subscriptions_plan_duration_positive`: `duration_days > 0`
- `subscriptions_plan_price_non_negative`: `price_rub >= 0`

---

### `Subscription`

Represents a specific grant of subscription access to a user. Multiple overlapping subscriptions per user are allowed (ADR 0009 D3).

| Field | Type | Attributes | Description |
|---|---|---|---|
| `id` | BigAutoField | Primary Key | Standard ID |
| `user` | ForeignKey | User, on_delete=CASCADE, related_name="subscriptions" | Subscription holder |
| `plan` | ForeignKey | Plan, on_delete=PROTECT, related_name="subscriptions" | Associated plan |
| `status` | CharField | max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True | `active`, `cancelled` |
| `starts_at` | DateTimeField | db_index=True | Start timestamp (UTC) |
| `expires_at` | DateTimeField | db_index=True | End timestamp (UTC) |
| `created_at` | DateTimeField | auto_now_add=True | UTC timestamp |
| `updated_at` | DateTimeField | auto_now=True | UTC timestamp |

Constraints:
- `subscriptions_sub_status_valid`: `status in ('active', 'cancelled')`
- `subscriptions_sub_dates_valid`: `expires_at > starts_at`

Indexes:
- Composite index on `(user, status, expires_at)` for optimal entitlement queries.
- Default ordering: `("-expires_at", "-id")`.
