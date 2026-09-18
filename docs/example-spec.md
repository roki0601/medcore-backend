# Example spec: password account and JWT lifecycle

> Это эталон implementation-ready spec для одного узкого auth slice. Он не
> закрывает Telegram protocol, password reset delivery или все profile features;
> они остаются отдельными specs и не должны быть выдуманы из этого файла.

**Status:** Ready for implementation  
**Owning app:** `users`  
**Risk:** High  
**Related docs:** `docs/architecture/auth-and-access.md`,
`docs/architecture/domain-model.md`, `docs/architecture/conventions.md`

## Goal

Дать пользователю возможность создать password account, войти, получать
короткоживущий access JWT, обновлять его через revocable refresh cookie,
посмотреть свой account и безопасно выйти.

## Scope

- custom `users.User` model based on Django auth;
- username/password registration and login;
- optional email persistence, без email verification;
- access JWT и refresh token/session;
- refresh через `httpOnly` cookie;
- CSRF bootstrap cookie/header contract for browser cookie endpoints;
- logout текущей refresh session;
- `GET /me`;
- change password с revoke всех refresh sessions;
- DRF permissions, throttling, CORS/CSRF configuration needed by these endpoints;
- migrations, OpenAPI schema и tests.

## Out of scope

- Telegram handshake, linking и unlinking;
- password reset delivery/verification;
- email verification;
- paid access, roles management и admin UI;
- profile fields university/course/goal/load;
- anonymous учебный content access;
- refresh rotation/reuse-detection; this slice explicitly uses non-rotating
  refresh tokens;
- frontend implementation.

## Actors

| Actor | Allowed actions |
|---|---|
| Anonymous | register, login, refresh with valid cookie |
| Authenticated user | `me`, logout, change own password |
| Editor/admin | same password flow; role assignment is outside scope |
| System | issue/validate/revoke tokens, hash passwords, log safe auth events |

## User scenarios

### Register

1. Anonymous sends unique username, password and optional email.
2. Backend validates input and creates active User with role `user`.
3. Backend returns `201`, access token and public user representation.
4. Backend sets refresh cookie and creates a persistent revocation record.

### Login

1. Anonymous sends username and password.
2. Backend verifies credentials and `is_active`.
3. Success returns `200`, access token, public user and refresh cookie.
4. Invalid credentials return the same public error shape regardless of whether
   username exists.

### Refresh

1. Client first obtains the CSRF cookie from `GET /auth/csrf/`, then sends
   `POST /auth/token/refresh/` with refresh cookie and CSRF header.
2. Backend validates signature, token type, expiry, User active state and
   non-revoked session.
3. Backend returns a new access token; the existing refresh token remains valid
   until expiry or explicit revoke. No rotation is implemented in this feature.

### Logout

1. Client sends `POST /auth/logout/` with the refresh cookie and CSRF header.
2. Backend revokes the current refresh session, clears the cookie and returns
   `204`.
3. Repeating logout is safe and still clears the cookie.

### Change password

1. Authenticated user sends current and new password.
2. Backend verifies current password, changes hash and revokes all the user’s
   refresh sessions in one transaction.
3. Response is `204`; the client must log in again.

## Entities

### User

Owned by `users`. Use a custom Django user model from the first migration.
`AbstractUser` is the default implementation base unless a later approved
decision requires another Django auth base.

Required semantic fields:

- `id`: `BigAutoField`;
- `username`: `CharField(max_length=150)`, required, stored in canonical trimmed
  lowercase form; enforce case-insensitive uniqueness with a PostgreSQL functional
  unique constraint on `Lower(username)` and the same normalization in model
  manager/save/admin paths;
- `password`: Django password hash only; Telegram-only accounts use Django's
  unusable-password state until a separate password-linking flow exists;
- `email`: `EmailField(max_length=254, null=True, blank=True)`, not unique;
- `telegram_id`: `BigIntegerField(null=True, blank=True, unique=True)`;
- `telegram_username`: `CharField(max_length=255, null=True, blank=True)`;
- `role`: `CharField(max_length=20)`, choices `user | editor | admin`, default
  `user`; this domain/API role is separate from Django `is_staff` and
  `is_superuser`, whose mapping is a later admin/roles spec;
- `is_active`: `BooleanField(default=True)`;
- `auth_version`: `PositiveIntegerField(default=0)`;
- `created_at`, `updated_at`: `DateTimeField`, timezone-aware.

### RefreshSession

Owned by `users`; one User has many sessions. Store only the token identifier
(`jti`) or a one-way representation sufficient for revocation, never the raw
cookie value. Required semantics: `id BigAutoField`, `user` FK, unique `jti`,
`auth_version`, `expires_at`, nullable `revoked_at`, `created_at`. Add an index
on `(user, revoked_at)` and `expires_at`.

## Business rules

1. Username is the password-flow login identifier.
2. Username is unique after trimming and lowercase normalization.
3. Password has at least 8 characters; Django password validators may reject
   stronger unsafe values.
4. Email is optional and is not used for login in this feature.
5. New users have role `user` and cannot self-assign editor/admin.
6. Inactive users cannot login, refresh or call authenticated endpoints.
7. Access JWT is sent only in Bearer header; refresh is sent only by cookie.
8. Refresh requires an unexpired, non-revoked session belonging to an active User.
9. Logout revokes only the current refresh session and is idempotent.
10. Password change revokes all refresh sessions for that User.
11. User and RefreshSession creation on registration is one transaction.
12. Login auth errors do not reveal whether a username exists. Registration
    intentionally returns `USERNAME_TAKEN` so the client can correct input.
13. `auth_version` is incremented on password change and is included in access
    and refresh claims/session records.

## Invariants

- unique normalized username;
- password hash is never equal to or derived as plaintext storage;
- RefreshSession jti is unique;
- revoked session can never refresh;
- inactive/deleted User cannot refresh;
- User deletion cascades/revokes owned sessions;
- password change increments `auth_version` and invalidates prior access/refresh
  credentials;
- no access/refresh token or password appears in logs or API response except the
  intended token fields.

## Data model

Migration must add the custom User model before other apps reference it.
`RefreshSession.user` uses `CASCADE`; `revoked_at` is nullable and immutable
except through token lifecycle services.

The migration must include the functional unique constraint on
`Lower(username)`; model manager, `save()` and admin form all use the same
canonicalization helper before the database constraint is evaluated.

No separate profile, Telegram identity, email verification or password reset
tables are introduced by this feature.

Use `djangorestframework-simplejwt` as the JWT signing/parsing dependency behind
the users adapter. Configuration is fixed for this spec: HS256 with a dedicated
environment-provided signing key, issuer `medcore-backend`, audience
`medcore-frontend`, access lifetime 15 minutes and refresh lifetime 30 days.
Claims include `sub`, `jti`, `token_type`, `iat`, `exp`, `iss`, `aud` and
`auth_version`. Refresh rotation is disabled; `RefreshSession` owns revocation.

The authentication class validates signature, issuer, audience, token type,
expiry, active User and current `auth_version` on every Bearer request. Refresh
also validates the `jti` record, its user/session match and revocation state.

## API

All URLs include `/api/v1/`. JSON uses `snake_case`.

Cookie/CSRF constants:

- refresh cookie: `medcore_refresh`, `HttpOnly`, `Path=/api/v1/auth/`,
  `Secure=true` and `SameSite=Lax` in the required production first-party
  topology; local same-site development may use `Secure=false`;
- CSRF cookie: Django `csrftoken`, not HttpOnly, same deployment Secure/SameSite
  policy;
- CSRF header: `X-CSRFToken`;
- `GET /api/v1/auth/csrf/` is anonymous, sets `csrftoken`, returns a masked token.
- frontend requests use `credentials: include`; credentialed CORS allows only the
  configured frontend origins.

Rate limits are fixed for this slice: registration 5/hour/IP, login
10/minute/IP and 5/minute/normalized username, refresh 30/minute/IP before
token validation plus 30/minute/session after successful validation. Throttling
storage must be shared across workers/instances in production.

### `GET /api/v1/auth/csrf/`

Anonymous. Sets the `csrftoken` cookie and returns `200` with a masked CSRF token:

```json
{"csrf_token": "<masked-token>"}
```

The frontend sends that token as `X-CSRFToken` and uses `credentials: include`.
The endpoint does not issue or refresh an auth token and is safe to repeat.

### `POST /api/v1/auth/register/`

Anonymous. Client must first obtain the CSRF cookie and send the CSRF header.
Request:

```json
{
  "username": "anna",
  "password": "correct horse battery",
  "email": "anna@example.com"
}
```

`email` is optional and may be `null`/omitted. Success `201`:

```json
{
  "access_token": "<jwt>",
  "token_type": "Bearer",
  "expires_in": 900,
  "user": {
    "id": 1,
    "username": "anna",
    "email": "anna@example.com",
    "role": "user"
  }
}
```

Response also sets `medcore_refresh` cookie with the attributes above and
configured 30-day expiry. Credentialed CORS is enabled only for configured
frontend origins.

### `POST /api/v1/auth/login/`

Anonymous. Client must first obtain the CSRF cookie and send the CSRF header.
Request contains `username` and `password`; success is the same shape as register
with status `200` and a new RefreshSession.

### `POST /api/v1/auth/token/refresh/`

Anonymous by DRF header semantics, but requires valid refresh cookie and CSRF
header. No request body. Success `200` returns only a new access token shape:

```json
{
  "access_token": "<jwt>",
  "token_type": "Bearer",
  "expires_in": 900
}
```

### `POST /api/v1/auth/logout/`

Requires the CSRF header; the refresh cookie is optional so the endpoint can
clear an already-missing cookie. A valid access token is optional, allowing logout
after the access token expires. Success `204`, clears cookie and revokes the
session. Missing/expired/revoked session is treated idempotently as logout
success after cookie clearing.

### `GET /api/v1/auth/me/`

Authenticated. Success `200`:

```json
{
  "id": 1,
  "username": "anna",
  "email": "anna@example.com",
  "role": "user"
}
```

### `POST /api/v1/auth/change-password/`

Authenticated with Bearer access JWT; this endpoint does not use cookie
authentication and therefore does not require CSRF. Request:

```json
{
  "current_password": "old password",
  "new_password": "new secure password"
}
```

Success `204`; all refresh sessions for User are revoked.

## Permissions

- CSRF bootstrap/register/login/refresh: anonymous entry points with throttling
  where specified; register, login and refresh require the CSRF header because
  they set or use the refresh cookie.
- Change password/me: authenticated User only. Logout authenticates the refresh
  session from the cookie and is intentionally available when access JWT expired.
- Role is returned but cannot be changed by these endpoints.
- No endpoint in this feature grants access to unpublished content or bypasses
  subscription policy.

## Validation

- trim username; reject empty, whitespace-only or invalid length;
- normalize username lowercase before uniqueness check;
- password length at least 8 and Django password validators enabled;
- email, when present, must be valid format and is stored normalized according to
  Django email convention;
- reject unknown write fields instead of silently accepting them;
- reject malformed JSON and wrong types with `VALIDATION_ERROR`.

## Errors

| Condition | Status | Code |
|---|---:|---|
| malformed/invalid request | 400 | `VALIDATION_ERROR` |
| username already exists | 409 | `USERNAME_TAKEN` |
| invalid username/password | 401 | `INVALID_CREDENTIALS` |
| inactive user | 401 | `INVALID_CREDENTIALS` |
| absent/invalid/expired/revoked refresh | 401 | `INVALID_REFRESH_TOKEN` |
| missing/invalid access JWT | 401 | `AUTHENTICATION_REQUIRED` |
| missing/invalid CSRF token | 403 | `CSRF_FAILED` |
| wrong current password | 400 | `INVALID_CURRENT_PASSWORD` |
| throttled | 429 | `RATE_LIMITED` |

Error body follows `docs/architecture/conventions.md`. Login credential errors
must not distinguish unknown user from wrong password. Logout is endpoint-specific:
with valid CSRF it returns `204` even when the session is already absent/expired;
`INVALID_REFRESH_TOKEN` applies to refresh, not idempotent logout.

Register, login, refresh and logout views must apply explicit `csrf_protect` (or
an equivalent DRF permission) and use a JSON CSRF failure handler that returns
`403 CSRF_FAILED`; relying on SessionAuthentication defaults is not sufficient.

## Edge cases

- two concurrent registrations with same normalized username: exactly one
  succeeds, the other receives `USERNAME_TAKEN` from database-protected handling;
- registration transaction rollback creates neither User nor session;
- logout after token expiry still clears cookie and remains idempotent;
- refresh after logout/password change fails;
- inactive user’s existing access token is rejected by the authentication layer;
- missing optional email does not block registration;
- password containing Unicode/whitespace is handled by Django validators, with no
  plaintext logging;
- a stale access/refresh credential issued before password change is rejected by
  `auth_version` validation;
- user deletion revokes sessions before/within cascade and leaves no usable token.

## Transactions

- Registration: `User` + `RefreshSession` creation in one `atomic` service.
- Login: credential check, session creation and response cookie setup; no partial
  user mutation.
- Logout: revoke current session in one write transaction, then clear cookie.
- Password change: verify old password, update hash and revoke all sessions in
  one `atomic` transaction while incrementing `auth_version`.

## Concurrency

- Database unique constraint is authoritative for username races.
- Revoke operations are idempotent updates; repeated logout has no error.
- Login, refresh and password change lock the User row first, then read/update
  sessions. This single lock order prevents a login from creating a session after
  password-change revoke-all and prevents refresh from passing an old
  `auth_version`; deterministic race tests are required.

## Background jobs/events

None. Auth operations are synchronous. No Celery, queue, event bus or email job is
introduced. Password reset/email delivery is a separate future spec.

## Security

- Django password hashing and validators;
- short-lived access token;
- refresh in `httpOnly` cookie, `Secure` in production, explicit SameSite;
- CSRF protection for browser cookie endpoints;
- CORS/trusted origins limited to configured frontend domains;
- throttling registration, login and refresh;
- explicit CSRF enforcement and JSON failure handling on every cookie endpoint;
- no secrets in logs, errors, fixtures or source;
- generic login credential errors to limit account enumeration; registration's
  deterministic conflict is an explicit usability/security trade-off;
- revoke sessions on password change and account deletion.

## Risks, compatibility and rollout

- This is a greenfield custom User migration; it must land before any foreign
  key to User and before frontend API integration.
- `username` is the password-flow identifier. The prototype's email login cannot
  be deployed against this contract without frontend adaptation.
- Production cookie auth requires first-party frontend/backend origins under the
  same registrable domain (for example `app.example` and `api.example`) or a
  same-origin backend proxy/BFF. Default `vercel.app` and `onrender.com`
  hostnames are not an accepted production topology for this cookie contract.
- JWT signing key, issuer/audience and cookie attributes are environment
  configuration; changing them invalidates active credentials and requires a
  coordinated rollout.
- Deploy database migrations before enabling endpoints. Rollback is a forward
  fix after User migration; applied auth migrations must not be rewritten.
- No existing backend clients exist, but OpenAPI is the compatibility artifact
  for the first frontend client.

## Acceptance criteria

1. A clean environment can migrate the custom User and RefreshSession schema,
   including canonical username normalization and functional uniqueness.
2. Valid registration returns `201`, public user, access token and refresh cookie.
3. Duplicate normalized username returns `409 USERNAME_TAKEN`.
4. Valid login returns `200` and creates a revocable refresh session.
5. Invalid credentials return generic `401 INVALID_CREDENTIALS`.
6. A valid refresh cookie returns a new access token.
7. Revoked/expired refresh cookie returns `401 INVALID_REFRESH_TOKEN`.
8. Logout revokes the current session, clears cookie and is idempotent.
9. `GET /me` requires valid access JWT and returns only public User fields.
10. Password change revokes all refresh sessions and requires the old password.
11. CSRF bootstrap returns a masked token, sets the cookie and supports a
    credentialed frontend request.
12. Auth endpoints are throttled; malformed/forged refresh attempts are covered
    by the IP bucket before token validation.
13. Cookie endpoints enforce explicit CSRF policy and return JSON `CSRF_FAILED`.
14. Tests and OpenAPI schema cover every endpoint and listed negative case.

## Test scenarios

- User model: normalized username uniqueness, password hash, role default,
  optional email, active flag;
- service: registration commit/rollback, login, refresh validation, logout,
  change-password revoke-all;
- API: success status/body/cookie, malformed input, duplicate, invalid auth,
  inactive user, CSRF bootstrap/header, throttling and endpoint-specific logout;
- JWT: wrong signature, issuer, audience, token type, expiry, unknown jti,
  user/session mismatch and stale auth_version;
- cookies/CORS: exact Set-Cookie attributes, deletion attributes, credentials
  include and disallowed origin;
- security: no password/token in logs and no sensitive fields in `/me`;
- concurrency: duplicate registration race and repeated logout;
- concurrency: login/refresh racing with password change and auth-version
  invalidation;
- CSRF: missing/invalid token on every cookie endpoint and JSON error envelope;
- migrations: clean migration and `makemigrations --check`.

## Dependencies

- Foundation/API bootstrap;
- PostgreSQL;
- Django auth and DRF;
- `djangorestframework-simplejwt`;
- configured CORS/CSRF and frontend origin;
- no Telegram or email provider dependency for this slice.

## Open questions

None for this password/JWT slice. Telegram protocol, password reset/email
delivery, profile preferences and payment/access remain explicitly out of scope
and are tracked globally in `docs/architecture/open-questions.md`.
