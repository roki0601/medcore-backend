# Subscriptions API Contract

Base URL: `/api/v1/subscriptions/`
Source of truth: `medcore-docs/decisions/0009-subscriptions-core-and-paid-entitlement.md` (ADR 0009)

All endpoints follow the standard MedCore REST conventions and error envelope.

---

## 1. List Available Plans

- **Endpoint**: `GET /api/v1/subscriptions/plans/`
- **Auth**: Public (`AllowAny`)
- **Description**: Returns all currently active subscription plans available for purchase.

### Response 200 OK

```json
[
  {
    "id": 1,
    "code": "monthly",
    "title": "Месячная подписка",
    "description": "Полный доступ ко всем платным темам и материалам на 30 дней",
    "price_rub": "990.00",
    "duration_days": 30
  },
  {
    "id": 2,
    "code": "yearly",
    "title": "Годовая подписка",
    "description": "Полный доступ ко всем платным темам и материалам на 365 дней со скидкой",
    "price_rub": "7990.00",
    "duration_days": 365
  }
]
```

---

## 2. Get Current Subscription and Entitlement

- **Endpoint**: `GET /api/v1/subscriptions/current/`
- **Auth**: Authenticated user (`IsAuthenticated`)
- **Description**: Returns caller's active entitlement status and their active subscription (with latest `expires_at`, breaking ties by newest `id`).

### Response 200 OK (With Active Subscription)

```json
{
  "has_access": true,
  "subscription": {
    "id": 42,
    "plan": {
      "id": 1,
      "code": "monthly",
      "title": "Месячная подписка",
      "duration_days": 30
    },
    "status": "active",
    "starts_at": "2026-09-01T00:00:00Z",
    "expires_at": "2026-10-01T00:00:00Z"
  }
}
```

### Response 200 OK (Without Active Subscription)

```json
{
  "has_access": false,
  "subscription": null
}
```

### Response 401 Unauthorized (If unauthenticated)

```json
{
  "code": "AUTHENTICATION_REQUIRED",
  "detail": "Authentication credentials were invalid or missing.",
  "fields": {}
}
```
