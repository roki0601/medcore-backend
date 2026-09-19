# Research: Telegram auth and user account

## Decision 1: Use the legacy Telegram Login Widget protocol

- **Decision**: Accept the payload fields returned by the approved legacy widget
  (`id`, optional profile fields, `auth_date`, `hash`) and verify the official
  sorted `key=value` data-check string with HMAC-SHA-256 using
  `SHA256(TELEGRAM_BOT_TOKEN)` as the key.
- **Rationale**: The feature and accepted ADR 0008 explicitly select the
  verified Telegram Login Widget. Official documentation at
  `https://core.telegram.org/widgets/login-legacy` defines the exact protocol.
  The current Telegram OIDC flow would be a protocol change outside this
  feature.
- **Alternatives rejected**: OIDC/Mini Apps, trusting a frontend `telegram_id`,
  or a client-only nonce. They are not the approved current contract.

## Decision 2: Persist replay protection in PostgreSQL

- **Decision**: Store a one-way digest of the complete verified canonical
  data-check string in a users-owned `TelegramLoginReplay` table with a unique
  constraint. Insert it atomically with User and RefreshSession creation.
- **Rationale**: Official HMAC verification proves integrity and
  `auth_date` proves freshness but neither is one-time use. Redis is approved
  as cache, and eviction/restart cannot satisfy the absolute replay invariant.
  A database uniqueness constraint gives deterministic race behavior.
- **Alternatives rejected**: `telegram_id + auth_date`, client IP-based keys,
  RefreshSession fields, raw payload storage and Redis-only `SETNX`.

## Decision 3: Use the existing project JWT baseline

- **Decision**: Add `djangorestframework-simplejwt`, configure HS256 with a
  dedicated environment key, issuer `medcore-backend`, audience
  `medcore-frontend`, 15-minute access and 30-day refresh lifetimes, claims
  `sub`, `jti`, `token_type`, `iat`, `exp`, `iss`, `aud`, `auth_version`, and
  no refresh rotation.
- **Rationale**: `docs/example-spec.md:174-183` is the project's existing
  implementation baseline and matches the accepted Bearer/access + HttpOnly
  refresh contract.
- **Alternatives rejected**: custom JWT cryptography, framework defaults with
  undocumented lifetimes, rotation/reuse policy and raw-token persistence.

## Decision 4: Use first-party cookie/CSRF defaults

- **Decision**: Set `medcore_refresh` as HttpOnly, `Path=/api/v1/auth/`,
  `SameSite=Lax`, Secure in production and host-only. Bootstrap Django's
  `csrftoken` cookie and require `X-CSRFToken` on Telegram login, refresh and
  current logout. Bearer-only profile and logout-all mutations do not require
  cookie CSRF.
- **Rationale**: The one-origin production decision makes Lax first-party
  cookies sufficient, while HttpOnly alone is not CSRF protection. The
  existing example spec defines names and header. Login is included because it
  creates a browser authentication cookie and is otherwise login-CSRFable.
- **Alternatives rejected**: `SameSite=None` without a topology need, wildcard
  CORS, relying only on HttpOnly, or leaving login CSRF to defaults.

## Decision 5: Use shared scoped throttles

- **Decision**: Use Redis-backed DRF scoped throttles: Telegram login
  10/minute/IP plus 5/minute/verified Telegram ID when available; refresh
  30/minute/IP before validation plus 30/minute/session after validation; account
  mutations 10/minute/user+IP.
- **Rationale**: Throttling is an accepted security requirement and the
  project example already fixes login and refresh rates. Redis is an approved
  shared cache and is suitable for counters, unlike durable replay state.
- **Alternatives rejected**: per-process counters, no limit, or using Redis as
  the replay ledger.

## Decision 6: Hard-delete accounts without tombstones

- **Decision**: Revoke sessions then physically delete User in one transaction;
  future learning-owned User FKs cascade in the learning app. A fresh verified
  login may create a new account without restoring old data. A stale access
  credential after deletion returns 401 and changes nothing.
- **Rationale**: The feature transaction explicitly deletes User, accepted MVP
  decisions require progress/attempt cascade, and no retention/tombstone
  contract exists. A stale stateless JWT cannot resolve an authenticated
  principal without adding a tombstone or authentication bypass.
- **Alternatives rejected**: soft-delete/tombstone identity retention, special
  404 authentication bypass, or users importing learning.
