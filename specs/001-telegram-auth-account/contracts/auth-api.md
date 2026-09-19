# Authentication API contract

All routes use `/api/v1/`, trailing slashes and JSON. Errors use:

```json
{
  "code": "AUTH_INVALID_TELEGRAM_PAYLOAD",
  "detail": "Telegram authentication payload is invalid.",
  "fields": {}
}
```

`fields` is optional for non-validation errors. No response contains raw
Telegram payloads, bot tokens, JWTs or refresh-cookie values.

## Security schemes

- Bearer access token: `Authorization: Bearer <access_token>`.
- Refresh: HttpOnly `medcore_refresh` cookie, `Path=/api/v1/auth/`,
  `SameSite=Lax`, Secure in production; the raw value is not returned in JSON.
- CSRF: obtain `GET /api/v1/auth/csrf/`, retain the Django `csrftoken` cookie,
  and send its masked value as `X-CSRFToken` on Telegram login, refresh and
  current logout. Bearer-only logout-all, profile PATCH and profile DELETE do
  not require cookie CSRF.

## Endpoints

### `GET /api/v1/auth/csrf/`

Anonymous. Sets/refreshes `csrftoken` and returns `200`:

```json
{"csrf_token": "<masked-token>"}
```

No JWT or refresh cookie is issued. Safe to repeat.

### `POST /api/v1/auth/telegram/`

Anonymous plus CSRF cookie/header. Request is the legacy Login Widget payload:

```json
{
  "id": 123456789,
  "first_name": "Anna",
  "last_name": "Example",
  "username": "anna_example",
  "photo_url": "https://t.me/i/userpic/…",
  "auth_date": 1700000000,
  "hash": "<64 lowercase hexadecimal characters>"
}
```

`id`, `auth_date` and `hash` are required. The backend verifies the sorted
canonical fields and HMAC before database writes, rejects stale/future payloads
and atomically consumes the canonical digest.

Success `200` sets `medcore_refresh` and returns:

```json
{
  "access_token": "<JWT>",
  "expires_in": 900,
  "user": {
    "id": 1,
    "username": "anna_example",
    "role": "user",
    "has_telegram": true,
    "is_active": true,
    "created_at": "2026-09-18T15:00:00Z",
    "updated_at": "2026-09-18T15:00:00Z"
  }
}
```

Errors: `400 INVALID_REQUEST`, `401 AUTH_INVALID_TELEGRAM_PAYLOAD` or
`AUTH_USER_INACTIVE`, `403 CSRF_FAILED`, `429 THROTTLED`.

### `POST /api/v1/auth/token/refresh/`

Anonymous transport with refresh cookie and CSRF header. Validates signature,
type, expiry, User active state, auth version, JTI session and revocation while
locking the session row. Returns `200` with a new access token and unchanged
refresh-session identity:

```json
{"access_token": "<JWT>", "expires_in": 900}
```

Errors: `401 AUTHENTICATION_REQUIRED`, `AUTH_REFRESH_REVOKED` or
`AUTH_USER_INACTIVE`; `403 CSRF_FAILED`; `429 THROTTLED`.

### `POST /api/v1/auth/logout/`

Refresh cookie plus CSRF header. Revokes only the current session, clears the
cookie and returns `204`; repeated logout is idempotent.

### `POST /api/v1/auth/logout-all/`

Bearer access token. Revokes all refresh sessions for the current User in one
transaction and returns `204`.

### `GET /api/v1/auth/me/`

Bearer access token. Returns the current user summary shown above. The raw
`telegram_id` is not returned; `has_telegram` is the presence indicator.

### `PATCH /api/v1/auth/me/`

Bearer access token. Only `username` is accepted. Input is normalized before
case-insensitive uniqueness validation. Success `200` returns the updated user
summary. A collision returns `409 USERNAME_TAKEN`; invalid length/characters
returns `422 VALIDATION_ERROR`.

### `DELETE /api/v1/auth/me/`

Bearer access token and JSON `{"confirmation": "DELETE"}`. Missing or wrong
confirmation returns `400 INVALID_REQUEST` and changes nothing. Success locks
the User, revokes sessions, deletes User and cascades present learning-owned
rows, then returns `204`. A stale token after hard deletion returns `401` and
changes nothing. A fresh verified Telegram login may create a new empty account.

## Common error mapping

| Condition | HTTP | Code |
|---|---:|---|
| malformed request | 400 | `INVALID_REQUEST` |
| invalid/stale/replayed Telegram payload | 401 | `AUTH_INVALID_TELEGRAM_PAYLOAD` |
| missing/expired Bearer | 401 | `AUTHENTICATION_REQUIRED` |
| revoked/invalid refresh session | 401 | `AUTH_REFRESH_REVOKED` |
| inactive persisted User | 401 | `AUTH_USER_INACTIVE` |
| invalid CSRF | 403 | `CSRF_FAILED` |
| username conflict | 409 | `USERNAME_TAKEN` |
| username validation | 422 | `VALIDATION_ERROR` |
| excessive requests | 429 | `THROTTLED` |

## OpenAPI requirements

Every endpoint is annotated with request/response serializers, status codes,
Bearer/cookie/CSRF descriptions and stable error responses. Local development
serves schema/docs publicly; production requires configured internal/staff
access. OpenAPI must never include real credentials or token values.
