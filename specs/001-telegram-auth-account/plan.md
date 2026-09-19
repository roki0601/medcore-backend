# Implementation Plan: Telegram auth and user account

**Branch**: `feature/001-telegram-auth-account`  
**Date**: 2026-09-18  
**Spec**: [spec.md](./spec.md)  
**Decision record**: [quorum decision](../../.omp/decisions/2026-09-18-001-telegram-auth-account-quorum.md)

## Summary

Implement the Telegram Login Widget authentication and self-account lifecycle in
`apps.users`. The backend verifies the legacy Telegram HMAC payload and
freshness before any write, atomically consumes a durable canonical-payload
replay digest, creates or finds the User by `telegram_id`, and issues a
short-lived Bearer access JWT plus a non-rotating refresh JWT in an HttpOnly
cookie. Refresh sessions are server-side revocable. Account endpoints expose
only the current user's profile, mutable application username, logout,
logout-all and self-delete. The deletion service revokes sessions and hard-
deletes User; future learning-owned User foreign keys cascade without a
users-to-learning import.

## Technical Context

**Language/Version**: Python 3.12  
**Framework**: Django + Django REST Framework  
**Authentication**: `djangorestframework-simplejwt`, HS256, dedicated
`JWT_SIGNING_KEY`, issuer `medcore-backend`, audience `medcore-frontend`  
**Storage**: PostgreSQL; Redis only for shared DRF throttle counters  
**Testing**: pytest, pytest-django, DRF APIClient  
**API**: REST/JSON under `/api/v1/`, drf-spectacular OpenAPI  
**Target Platform**: Linux server, Docker/Compose deployment  
**Project Type**: Django modular monolith backend  
**Token lifetimes**: access 15 minutes; refresh 30 days; refresh rotation off  
**Telegram freshness**: `auth_date` max age 86400 seconds; future skew 60 seconds  
**Cookie policy**: `medcore_refresh`, HttpOnly, `Path=/api/v1/auth/`,
`SameSite=Lax`, Secure in production, host-only; `csrftoken` plus
`X-CSRFToken`  
**Throttles**: Telegram 10/minute/IP plus 5/minute/verified Telegram ID when
available; refresh 30/minute/IP before validation plus 30/minute/session after;
account mutations 10/minute/user+IP  
**Constraints**: no raw Telegram payload, bot token, JWT or refresh cookie in
storage/logs; no signals, repositories, queues or users→learning dependency;
preserve applied migrations and add forward migrations only  
**Scope**: Telegram-only MVP auth; password/email login, linking, unlink,
subscriptions, preferences and frontend remain out of scope

## Constitution Check

| Gate | Result | Evidence |
|---|---|---|
| Source-of-truth precedence | PASS | Quorum record resolves the feature-level gaps without overriding accepted ADRs. |
| Domain ownership | PASS | `users` owns auth/account; `common` only owns error/CSRF primitives; learning remains owner of learning rows. |
| Contract-first API | PASS | `spec.md` and `contracts/auth-api.md` define every endpoint, status and error envelope before implementation. |
| Security boundary | PASS | Legacy HMAC verification, durable replay uniqueness, JWT validation, CSRF, throttling and safe logging are explicit. |
| Data/migration safety | PASS | Forward migration only; PostgreSQL uniqueness/indexes and transaction boundaries are planned. |
| MVP simplicity | PASS | One Django app, direct ORM, SimpleJWT and existing Redis cache; no new queue/provider/abstraction layer. |
| Test evidence | PASS | Tests cover happy paths, permissions, errors, replay, races, CSRF, throttles and deletion. |

## Design decisions

1. **Owning app**: keep models, services, serializers, views, URLs,
   authentication and throttles in `apps/users`. Add only reusable error and
   CSRF response primitives to `apps/common`.
2. **Telegram protocol**: implement the official legacy Login Widget
   `data-check-string` and HMAC-SHA-256 algorithm. Verify the payload and
   freshness outside the write transaction.
3. **Replay**: add `TelegramLoginReplay` with a unique SHA-256 digest of the
   complete canonical verified data-check string. Insert it atomically before
   User/session creation. Keep rows for MVP; index `expires_at` for later
   reviewed operational cleanup.
4. **User lookup**: query by unique `telegram_id`, never application username.
   Use a deterministic usable Telegram username when valid; otherwise generate
   a unique `user_<telegram_id>` fallback. Existing application username is
   never changed from Telegram username updates.
5. **Tokens**: use SimpleJWT configured from environment settings. Store only
   refresh JTI and lifecycle state in `RefreshSession`; validate JTI, user,
   auth version, expiry and revocation on refresh.
6. **Account deletion**: `delete_account` locks the User, revokes sessions and
   hard-deletes User in one transaction. Learning-owned rows are expected to
   use `on_delete=CASCADE` in feature 003; users does not import learning. A
   stale token after deletion returns 401 and never recreates data.
7. **Errors**: add a common DRF exception handler and CSRF failure view that
   return `{code, detail, fields}` without traceback or secrets. Auth-specific
   failures use the stable codes from the spec.
8. **OpenAPI/deployment**: annotate all auth endpoints and document Bearer,
   refresh-cookie and CSRF requirements. Keep schema/docs public locally and
   require configured internal/staff access in production.

## Research summary

- Official legacy Telegram documentation confirms payload fields, sorted
  `key=value` canonicalization, SHA-256(bot-token) HMAC and optional freshness
  checking; it does not provide one-time replay storage.
- `docs/example-spec.md` provides the existing project baseline for SimpleJWT,
  claims, lifetimes, cookie/CSRF names and shared throttling. The quorum record
  explicitly adopts that baseline for this feature.
- PostgreSQL uniqueness plus an atomic transaction is the project convention
  for races. Redis remains cache/throttle storage, not durable auth state.

## Project structure

```text
apps/common/
├── exceptions.py              # stable error envelope / DRF exception handler
└── views.py                    # health plus CSRF bootstrap/failure views

apps/users/
├── models.py                   # User constraints, RefreshSession, replay ledger
├── services.py                 # verify/login, token lifecycle, account use cases
├── authentication.py           # SimpleJWT Bearer auth + auth_version checks
├── schema.py                   # drf-spectacular Bearer authentication scheme
├── serializers.py              # request/response boundary validation
├── views.py                    # thin endpoint orchestration and schema metadata
├── urls.py                     # /api/v1/auth/ routes
├── throttles.py                # scoped Redis-backed abuse limits
├── admin.py                    # safe lifecycle fields, no secrets
├── migrations/0002_*.py        # forward schema changes
└── tests/
    ├── test_models.py
    ├── test_services.py
    ├── test_authentication.py
    └── test_api.py

config/
├── settings/base.py            # REST auth, SimpleJWT, cookies, throttles
├── settings/production.py     # production cookie/schema access defaults
└── urls.py                     # include users routes and schema policy

specs/001-telegram-auth-account/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/auth-api.md
└── tasks.md
```

## Implementation order

1. Add SimpleJWT dependency and environment/settings primitives.
2. Add common error/CSRF envelope behavior and model/migration changes.
3. Implement Telegram verification, replay consume, username generation and
   token/session services.
4. Implement Bearer authentication and thin auth/account endpoints with OpenAPI
   annotations.
5. Add tests story-by-story, then test OpenAPI, throttling and deployment
   security behavior.
6. Run narrow checks, all project checks, final DeepSeek review, commit and
   publish only the feature branch.

## Risks and mitigations

- **Replay ledger growth**: retain non-secret digest rows for invariant safety;
  expose an indexed expiry for future separately reviewed cleanup.
- **Concurrent first login**: rely on unique `telegram_id` plus a narrow retry;
  keep replay consume and session creation in one atomic transaction.
- **Refresh/logout race**: lock the RefreshSession while checking revocation and
  updating `last_used_at`.
- **Existing usernames longer than 30**: migration must fail loudly or report
  invalid rows rather than silently truncate; the migration plan includes a
  preflight/data policy and tests.
- **Production cookie topology**: use one first-party origin and explicit
  configured CORS/CSRF trusted origins; local settings remain testable.
- **Learning deletion contract**: feature 003 must use the decision-recorded
  User FK cascade; feature 001 must not import that app.

## Complexity Tracking

No constitution violations. No Repository/UnitOfWork/EventBus layer, queue,
new provider or unrelated domain refactor is introduced.
