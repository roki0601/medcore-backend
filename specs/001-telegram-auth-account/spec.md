# Spec: Telegram auth and user account

Status: Ready for implementation after delegated quorum; decision record:
`.omp/decisions/2026-09-18-001-telegram-auth-account-quorum.md`
Owning apps: `users`; `common` supplies only domain-agnostic primitives.

Risk: High

Related architecture: docs/architecture/auth-and-access.md,
docs/architecture/conventions.md

Related decisions: medcore-docs/decisions/0008-mvp-auth-content-and-integration-contract.md

## Goal

Дать пользователю единственный согласованный MVP-flow регистрации и входа через
Telegram, после которого backend выдаёт Bearer access JWT и refresh JWT в
HttpOnly cookie. Пользователь должен иметь изменяемый username приложения, но
аутентификация всегда должна опираться на уникальный telegram_id.

## Scope

- Проверка payload Telegram Login Widget на backend.
- Создание или поиск User по telegram_id.
- Генерация username при первом входе и изменение username через account API.
- Access JWT, refresh cookie, refresh-session revocation.
- Получение текущего профиля.
- Logout текущей сессии и logout всех сессий.
- Self-service account deletion с отзывом сессий.
- Throttling, CSRF, безопасные ошибки и OpenAPI-контракт.

## Out of scope

- Регистрация или вход по password/email.
- Password reset и change password.
- Linking нескольких identity к одному User.
- Unlink Telegram.
- Email verification.
- Subscription/payment/trial semantics.
- Profile preferences: university, course, semester, daily load, selected subjects.
- UI и frontend implementation.

## Actors

| Actor | Разрешённые действия |
|---|---|
| anonymous | получить CSRF cookie, отправить Telegram login, обновить сессию по refresh cookie |
| user | читать и менять собственный username, logout, logout-all, удалить свой аккаунт |
| editor/admin | те же account actions для собственного аккаунта; роль не даёт обхода auth safeguards |
| Telegram | внешний источник подписанного login payload |

## User scenarios

### User Story 1 — Telegram login (P1)

Пользователь открывает frontend, проходит Telegram Login Widget и получает
авторизованную сессию.

Acceptance scenarios:

1. Given корректный неповторно используемый Telegram payload, when backend
   проверяет его, then создаётся User с telegram_id и выдаются access token и
   refresh cookie.
2. Given существующий User с тем же telegram_id, when он входит повторно, then
   создаётся новая refresh session без дублирования User.
3. Given payload с неправильной подписью, просроченным auth_date или отсутствующим
   telegram_id, when он отправлен, then backend возвращает 401 и не создаёт
   пользователя.

### User Story 2 — account username (P1)

Пользователь может задать или изменить username приложения.

Acceptance scenarios:

1. Given свободный валидный username, when user sends PATCH me, then username
   меняется и Telegram identity остаётся прежней.
2. Given занятый username, when user sends PATCH me, then backend возвращает
   409 и сохраняет прежнее значение.
3. Given Telegram username изменился, when user logs in again, then application
   username не меняется автоматически.

### User Story 3 — session lifecycle (P1)

Пользователь может обновлять access token и отзывать сессии.

Acceptance scenarios:

1. Given действующий refresh cookie, when user calls refresh, then выдаётся новый
   access token, а refresh token не ротируется.
2. Given revoked refresh session, when user calls refresh, then backend returns
   401 and clears the cookie.
3. Given logout-all, when any old refresh session is reused, then refresh fails.

### User Story 4 — self-delete (P2)

Пользователь может удалить аккаунт и связанные персональные данные.

Acceptance scenarios:

1. Given authenticated user and explicit delete confirmation, when DELETE me is
   called, then user sessions, progress, reviews and attempts are revoked or
   deleted according to their owning specs.
2. Given unauthenticated or missing confirmation request, when DELETE me is
   called, then no data is changed.

## Entities

- User: account owner. In this MVP it has a unique telegram_id, mutable unique
  application username, role, active state and timestamps.
- RefreshSession: server-side lifecycle record for a non-rotating refresh JWT,
  with expiry and revoked state.
- Telegram login payload: verified request input, never persisted as a secret.
- TelegramLoginReplay: users-owned ledger of a non-secret digest of the
  canonical verified Telegram payload, with unique digest and expiry metadata.

Existing Django password and email columns are not removed by this spec; they are
not a public authentication flow until a future approved spec.

## Business rules

1. Telegram Login Widget is the only registration/login entry point.
2. Backend verifies Telegram signature and freshness; frontend-provided
   telegram_id is never trusted by itself.
3. telegram_id is unique and is the canonical account lookup key.
4. username is unique case-insensitively, mutable, and is not an auth identity.
5. Username is 3–30 characters, normalized to NFKC, trimmed and lower-cased;
   allowed characters are latin letters, digits, dot, underscore and hyphen.
6. If Telegram provides no usable username, backend generates a unique
   user_<telegram_id> username.
7. New users receive role user and active state.
8. Access token is sent in the JSON response and is not stored in PostgreSQL as a
   session record.
9. Refresh JWT is stored in an HttpOnly cookie, is not rotated, and is revoked
   through RefreshSession.
10. Logout is idempotent and revokes only the current refresh session.
11. Logout-all revokes all refresh sessions for the User.
12. Inactive or deleted users cannot login, refresh or call authenticated APIs.
13. A fresh verified payload for a deleted Telegram account may create a new
    User with no prior account data; a stale credential cannot authenticate.
14. Exact replay of a verified payload is rejected by the unique replay ledger
    before User or RefreshSession state is committed.

## Invariants

- No two active Users share telegram_id.
- No two Users share username ignoring case.
- A revoked refresh session can never refresh successfully.
- Raw refresh JWT and Telegram verification secrets are not stored or logged.
- Account deletion revokes sessions in the same business operation.

## Data model

### User changes

- telegram_id: BigInt, unique; required for newly created Telegram users.
- username: existing string field, unique case-insensitively, mutable.
- role: user/editor/admin, default user.
- is_active: boolean, default true.
- created_at and updated_at: timezone-aware UTC timestamps.

No Telegram identity table is introduced.

### RefreshSession

- user: required foreign key to User.
- token identifier/hash: required and non-secret representation.
- expires_at: required UTC timestamp.
- revoked_at: nullable UTC timestamp.
- created_at and last_used_at: UTC timestamps.
- index by user and active/expiry state.

### TelegramLoginReplay

- digest: required one-way digest of the complete canonical verified
  data-check string; unique and never reversible to the raw payload.
- expires_at: required UTC timestamp for freshness/operational inspection.
- created_at: required UTC timestamp.
- Raw Telegram payload, bot token and JWTs are never stored.

## API

All URLs use /api/v1/ and trailing slashes.

### GET /api/v1/auth/csrf/

Authentication: anonymous allowed.

Success: 200, sets CSRF cookie and returns a masked token or status payload.
The endpoint does not issue a JWT and is safe to repeat.

### POST /api/v1/auth/telegram/

Authentication: anonymous allowed; Telegram verification required.

Request: Telegram Login Widget payload as received from the approved frontend
adapter. Backend validates signature, auth_date freshness and required identity
claims.

Success: 200 with access_token, expires_in and user summary; sets refresh cookie.

### POST /api/v1/auth/token/refresh/

Authentication: refresh cookie and valid CSRF header.

Success: 200 with a new access_token and unchanged refresh-session identity.

### POST /api/v1/auth/logout/

Authentication: refresh cookie and valid CSRF header.

Success: 204 or 200 with an empty success body. Repeated logout is idempotent.

### POST /api/v1/auth/logout-all/

Authentication: Bearer access token plus valid CSRF header if the deployment
uses cookie-authenticated state change.

Success: 204 or 200. All User refresh sessions are revoked.

### GET /api/v1/auth/me/

Authentication: Bearer access token.

Success: 200 with id, username, role, telegram_id presence indicator, active
state and timestamps. Verification secrets and refresh state are excluded.

### PATCH /api/v1/auth/me/

Authentication: Bearer access token.

Request: partial object with username only in the first version.

Success: 200 with updated user summary.

### DELETE /api/v1/auth/me/

Authentication: Bearer access token.

Request: explicit confirmation required, for example confirmation=DELETE.

Success: 204. Sessions are revoked and user-owned learning data is removed by
the owning learning services/cascade contract.

## Permissions

| Endpoint | anonymous | user | editor | admin |
|---|---:|---:|---:|---:|
| csrf | allow | allow | allow | allow |
| telegram login | allow | allow | allow | allow |
| refresh | cookie only | own cookie | own cookie | own cookie |
| logout/logout-all | no | own sessions | own sessions | own sessions |
| me read/update/delete | no | own user | own user | own user |

Admin role does not allow reading or revoking another user's sessions through
this account API. Administrative user management is a separate future scope.

## Validation

- Telegram payload must contain the required verified identity and freshness
  fields; malformed or stale payloads fail before User creation.
- username is normalized before uniqueness checks.
- empty, whitespace-only, too short, too long or unsupported-character usernames
  are rejected.
- username collision returns a stable conflict.
- DELETE me requires explicit confirmation and an authenticated User.
- refresh cookie and CSRF header are required on cookie-authenticated state
  changes.

## Errors

Every error uses the backend envelope:

    {
      "code": "AUTH_INVALID_TELEGRAM_PAYLOAD",
      "detail": "Telegram authentication payload is invalid.",
      "fields": {}
    }

| Condition | HTTP | Code |
|---|---:|---|
| malformed request | 400 | INVALID_REQUEST |
| invalid/stale Telegram payload | 401 | AUTH_INVALID_TELEGRAM_PAYLOAD |
| missing/expired Bearer token | 401 | AUTHENTICATION_REQUIRED |
| revoked refresh session | 401 | AUTH_REFRESH_REVOKED |
| invalid CSRF | 403 | CSRF_FAILED |
| username conflict | 409 | USERNAME_TAKEN |
| username validation failure | 422 | VALIDATION_ERROR |
| inactive User | 401 | AUTH_USER_INACTIVE |
| stale credential after deletion | 401 | AUTHENTICATION_REQUIRED |
| excessive requests | 429 | THROTTLED |

Error details never reveal Telegram bot secrets, JWTs or internal traceback.

## Edge cases

- Telegram user has no username: generate a unique fallback.
- Telegram username changes: do not mutate application username.
- Two first logins race for the same telegram_id: unique constraint resolves the
  race and the losing request returns the existing User/session safely.
- Two username updates race: database unique constraint returns one conflict.
- Refresh and logout race: a refresh observed after revocation fails.
- Account deletion first returns 204 after revoking sessions and deleting the
  User. A later request with a stale access credential returns 401 without
  changing data; it does not create a tombstone. A later fresh verified
  Telegram payload may create a new User without restoring deleted data.

## Transactions

- User lookup/create, replay-ledger consume and first RefreshSession creation
  are one atomic operation after Telegram HTTP verification completes.
- Username update and uniqueness validation are one atomic operation.
- Logout revocation is one idempotent update.
- Logout-all revokes all sessions in one transaction.
- Account deletion locks the User, revokes sessions, and physically deletes the
  User in one transaction; future learning-owned User FKs cascade in the
  owning app without a users-to-learning import.
- Telegram HTTP verification is completed before opening the database write
  transaction.

## Concurrency

- Enforce telegram_id and case-insensitive username uniqueness in the database.
- Use a transaction and retry only the specific unique-race path.
- Refresh revocation must be checked while updating session usage state.

## Background jobs/events

None. Telegram verification and token lifecycle are synchronous.

## Security

- Store Telegram bot/token secrets only in environment-backed secret storage.
- Verify the legacy Login Widget HMAC data-check string before any database
  write; reject `auth_date` older than 86400 seconds or more than 60 seconds
  in the future.
- Replay protection uses a PostgreSQL unique digest ledger and an atomic insert;
  Redis is used only for shared throttling counters, never as replay state.
- Use HS256 JWTs with a dedicated environment signing key, issuer
  `medcore-backend`, audience `medcore-frontend`, 15-minute access lifetime,
  30-day refresh lifetime, and claims `sub`, `jti`, `token_type`, `iat`, `exp`,
  `iss`, `aud` and `auth_version`; refresh tokens are not rotated.
- Refresh cookie is `medcore_refresh`, HttpOnly, `Path=/api/v1/auth/`,
  `SameSite=Lax`, Secure in production and host-only. CSRF uses Django's
  `csrftoken` cookie and `X-CSRFToken` header.
- Require CSRF cookie/header for Telegram login, refresh and current logout.
  Bearer-only logout-all, profile PATCH and profile DELETE do not require a
  cookie CSRF header.
- Apply shared Redis-backed throttling: Telegram login 10/minute/IP plus
  5/minute/verified Telegram ID when available; refresh 30/minute/IP before
  validation plus 30/minute/session after validation; account mutations
  10/minute/user+IP.
- Restrict CORS and CSRF trusted origins to the configured frontend origin.
- Do not trust frontend-supplied telegram_id without signature verification.
- Never log raw Telegram payload, JWT, cookie or secret.

## Risks, compatibility and rollout

- Existing User migration currently contains password/email fields and optional
  Telegram columns. The implementation must preserve existing applied migration
  history and decide any nullability backfill in the plan.
- The frontend prototype's email demo login is not a contract and must be
  replaced by Telegram flow.
- Exact Telegram verification constants must be checked against official
  Telegram documentation during implementation.
- This feature requires coordinated frontend/backend auth rollout.

## Acceptance criteria

1. A valid Telegram Login Widget payload creates or finds exactly one User.
2. Invalid, stale and replayed payloads cannot authenticate.
3. User lookup uses telegram_id, not username.
4. Username can be changed under the documented validation and uniqueness rules.
5. Refresh uses HttpOnly cookie, does not rotate the refresh token and respects
   revocation.
6. Logout and logout-all revoke the documented sessions.
7. Self-delete revokes sessions and removes user-owned learning data.
8. All endpoint errors use stable codes and no secrets leak.
9. OpenAPI describes all auth endpoints and cookie/header requirements.

## Test scenarios

- Model constraints for telegram_id and case-insensitive username.
- Telegram signature, stale payload, replay and malformed payload.
- First login, repeat login and concurrent first login.
- Username normalization, invalid values and collision.
- Access token authentication, expired token and inactive user.
- Refresh success, revoked refresh and logout race.
- Logout current session and logout-all.
- CSRF success/failure on cookie endpoints.
- Account deletion confirmation, cascade and repeated request.
- Throttling and safe logging assertions.

## Dependencies

- Existing custom users.User model.
- PostgreSQL migrations.
- DRF authentication and permission configuration.
- Secret configuration for Telegram verification.
- Frontend Telegram Login Widget integration.
- Learning account-deletion contract from spec 003.

## Open questions

None for the MVP behavior. The delegated quorum resolved timestamp/replay
policy, deletion retention semantics, JWT/cookie/CSRF baseline and throttling;
the implementation must follow the decision record above and the official
legacy Telegram Login Widget verification algorithm.
