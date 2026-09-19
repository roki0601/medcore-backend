# Delegated quorum decision: Telegram auth and user account

- Feature: `001-telegram-auth-account`
- Workflow state: `SPEC_REVIEW` → `READY_FOR_IMPLEMENTATION`
- Decision status: accepted for this feature implementation
- Decision time: 2026-09-18T15:16:53Z
- Review roles and model identifiers:
  - Qwen `spec-reviewer`: `ufanet-local/Qwen3-Coder-Next-NVFP4`
  - Luna `watchdog`: `openai-codex/gpt-5.6-luna:high`
  - DeepSeek `architect`: `openrouter/deepseek/deepseek-v4.1-flash:max`

## Question and affected workflow

Feature 001 is high-risk authentication/account work. The draft contract required
Telegram payload freshness and replay rejection, self-delete with learning-data
cleanup, and revocable JWT sessions, but left several security and
cross-domain implementation contracts unstated. The workflow could not advance
from `SPEC_REVIEW` until the delegated quorum resolved those gaps without
silently overriding an accepted decision.

## Authoritative evidence

- `AGENTS.md:27-32,52-61,71-85,107-127` — unresolved `TBD`, auth/security,
  migration, cross-domain and public-API decisions require evidence-backed
  quorum and a decision record; users owns account/auth; no unsafe logging.
- `PROJECT_STATE.md:9-17,29-42,55-59` — feature is high risk and remains in
  `SPEC_REVIEW` until unanimous Qwen/Luna/DeepSeek review and required records.
- `specs/001-telegram-auth-account/spec.md:61-68,120-145` — verified
  Telegram payload, freshness, replay rejection, canonical `telegram_id`,
  revocable non-rotating refresh session, and inactive-user rules.
- `specs/001-telegram-auth-account/spec.md:222-229,262-300,302-321,334-357` —
  self-delete, error codes, deletion edge case, transactions/concurrency,
  throttling, CSRF, OpenAPI and required tests.
- `specs/001-telegram-auth-account/spec.md:107-165,178-220` — User and
  RefreshSession data contract and endpoint shape.
- `specs/003-learning-state/spec.md:100-108,155-193,303-312,368-379` —
  learning-owned User rows and the existing gap: only content-deletion
  cascading is specified, not User-account deletion.
- `docs/architecture/target-architecture.md:67-76,81-121,145-181,198-231` —
  users owns auth/account lifecycle, learning owns learning state, common owns
  only domain-agnostic primitives, dependency direction, service transactions,
  revocable cookies and shared throttling/logging constraints.
- `docs/architecture/domain-model.md:62-73,159-188` — User/refresh ownership,
  learning lifecycle, User-deletion cascade direction and uniqueness invariants.
- `docs/architecture/auth-and-access.md:21-32,78-118,130-148` — legacy
  Telegram verification boundary, Bearer/access and HttpOnly refresh semantics,
  CSRF requirement for cookie state changes, and inactive/deleted-user behavior.
- `docs/architecture/conventions.md:34-74,76-109,132-156` — error envelope,
  validation layers, transaction/constraint requirements and entity-specific
  deletion policy.
- `docs/architecture/open-questions.md:14-22,47-52` — timestamp/replay and
  account-deletion retention were explicitly open until this feature contract
  discloses them.
- `../medcore-docs/decisions/0004-mvp-decision-register.md:161-183` —
  self-delete, cascade of progress/attempts, unique username/telegram ID,
  throttling and CSRF are accepted MVP requirements.
- `../medcore-docs/decisions/0008-mvp-auth-content-and-integration-contract.md:23-41,91-109` —
  Telegram-only current MVP, direct User fields, non-rotating revocable refresh,
  and password/linking deferral.
- Official legacy Telegram Login Widget protocol:
  `https://core.telegram.org/widgets/login-legacy`, sections “Receiving
  authorization data” and “Checking authorization” — fields, sorted
  `key=value` data-check string, SHA-256(bot token) HMAC, and `auth_date`
  freshness check; the protocol does not provide one-time replay state.
- `docs/example-spec.md:121-127,174-183,189-204` — existing backend example
  baseline for RefreshSession/JTI, JWT claims/lifetimes, cookie/CSRF constants
  and shared throttle rates. It is used as implementation evidence, not as a
  silent product override.

## Independent initial findings

### Qwen spec-reviewer

Initial verdict: `READY`. The feature was complete at the acceptance-criteria
level, with implementation details for RefreshSession, `is_active`, throttling
and OpenAPI. Qwen did not initially identify the replay/deletion contract gaps.

### Luna watchdog

Initial verdict: `BLOCKED` for:

1. absent User-deletion contract across users/learning;
2. replay rejection without nonce/ledger/retention/atomicity;
3. hard-delete versus tombstone/re-registration ambiguity;
4. the `users, common` owner header conflicting with the architecture's users
   ownership and common-only primitives;
5. unstated freshness, JWT lifetime, cookie and CSRF security parameters.

### DeepSeek architect

Initial verdict: `BLOCKED` for the same replay, cross-domain deletion,
retention, auth/token/CSRF and operational contracts, plus current username
schema/validation not matching the 3–30 character feature invariant.

## Deliberation and rebuttal

### Round 1

All reviewers independently agreed that HMAC plus `auth_date` is not one-time
replay protection and that the feature's learning-deletion dependency is absent
from spec 003. Qwen first suggested a payload record but proposed an unsafe
`telegram_id + auth_date + client_ip` key; the watchdog explicitly rejected
that key because a replay from another IP would bypass it. Luna and DeepSeek
proposed a persistent PostgreSQL ledger keyed by the canonical verified payload,
with a unique constraint and atomic consume before User/session writes. All
reviewers rejected Redis-only replay state because the architecture approves
Redis as cache and eviction/restart cannot prove the replay invariant.

For deletion, all reviewers converged on a users-owned service that revokes
sessions and hard-deletes User while learning-owned rows use database
`ON DELETE CASCADE`; users must not import learning. They rejected silently
calling a learning service or inferring subscription/media/audit retention.

For retention, Luna and DeepSeek initially classified hard-delete versus
 tombstone as a material decision. The evidence favored hard deletion because
 the feature transaction explicitly deletes User, no tombstone/retention is
 accepted, and the architecture leaves retention entity-specific. A later
 verified Telegram login therefore creates a new account with no old data.

### Round 2

The shared findings produced unanimous agreement on the users/learning
boundary and durable replay ledger. Qwen initially treated some JWT/CSRF/TTL
values as local details; Luna and DeepSeek challenged that under the explicit
AGENTS auth/security gate. The quorum then agreed that the written decision
must fix the security baseline rather than import framework defaults silently.

### Round 3

The remaining disagreement was repeated DELETE behavior. A physical delete
leaves no authenticated principal, so a special 404 path would require an
authentication bypass or tombstone. The quorum rejected that extra state and
adopted the existing feature error semantics: first DELETE returns 204; a stale
Bearer token after hard deletion cannot authenticate and receives 401 with no
state change. The feature edge wording must be amended in the implementation
contract to permit this stateless-auth outcome. A fresh verified Telegram
payload may create a new account; no old data is recreated.

The final round also converged on the security values below. Qwen confirmed no
substantive dissent on the 86,400-second freshness baseline.

## Final decision

### 1. Account ownership and deletion

- `users` owns the account-deletion service and all RefreshSession lifecycle.
- In one `transaction.atomic` operation, lock the User, revoke all of that
  User's RefreshSession rows, then physically delete the User.
- Future learning-owned rows named by spec 003 — UserTopicProgress,
  UserTopicSectionProgress, FlashcardReview and QuizAttempt — must reference
  User with database `ON DELETE CASCADE`. This is the cross-domain contract;
  `users` does not import `learning` or call a reverse dependency.
- Do not infer deletion/retention behavior for subscriptions, media, audit rows
  or future domains; those remain their owning specs' responsibility.
- First authenticated DELETE returns 204. A later request with a stale access
  credential returns 401 and changes nothing; use `AUTHENTICATION_REQUIRED`
  when no principal can be resolved, and `AUTH_USER_INACTIVE` only when an
  inactive persisted User is identified.
- A later fresh verified Telegram payload may create a new User with a new
  account state. No prior User data is restored. This is not account linking.

### 2. Telegram replay and freshness

- Support the accepted legacy Telegram Login Widget payload, not a protocol
  switch to OIDC or Mini Apps.
- Verify the official sorted data-check string and HMAC-SHA-256 using
  `SHA256(TELEGRAM_BOT_TOKEN)` before opening a database write transaction.
- Reject `auth_date` older than 86,400 seconds or more than 60 seconds in the
  future, using UTC server time.
- Add a users-owned PostgreSQL replay ledger with a one-way SHA-256 digest of
  the complete canonical verified data-check string (not only ID/time), an
  expiry/created timestamp and a unique digest constraint. Never store raw
  payloads, bot tokens or JWTs.
- Insert the digest atomically in the same transaction as User and
  RefreshSession creation. A unique conflict is `AUTH_INVALID_TELEGRAM_PAYLOAD`
  for an exact replay; a fresh payload for the same Telegram User is allowed.
- Retain replay rows for the MVP rather than deleting them in an auth request;
  `expires_at` supports indexed operational inspection. No Redis-only replay
  store or background queue is introduced. Table growth is a documented
  residual risk and future cleanup must preserve the unique/replay invariant.

### 3. JWT, cookie, CSRF and throttling baseline

- Use `djangorestframework-simplejwt` with HS256 and a dedicated
  environment-provided signing key (`JWT_SIGNING_KEY`), issuer
  `medcore-backend`, audience `medcore-frontend`, 15-minute access lifetime
  and 30-day refresh lifetime. Refresh rotation is disabled.
- Claims include `sub`, `jti`, `token_type`, `iat`, `exp`, `iss`, `aud` and
  `auth_version`. RefreshSession stores unique JTI plus non-secret lifecycle
  state; raw refresh JWT is never persisted or logged.
- Refresh cookie is `medcore_refresh`, HttpOnly, `Path=/api/v1/auth/`,
  `SameSite=Lax`, Secure in production and host-only (no broad Domain). Local
  same-site development may use Secure=false. CSRF cookie is Django's
  non-HttpOnly `csrftoken`; clients send `X-CSRFToken`.
- `GET /api/v1/auth/csrf/` bootstraps the CSRF cookie. Require the CSRF cookie
  and header for Telegram login (login-CSRF defense), refresh and current
  logout. Bearer-only `logout-all`, profile PATCH and profile DELETE do not
  require a cookie CSRF header.
- Use shared Redis-backed DRF throttles: Telegram login 10/minute/IP plus
  5/minute/verified Telegram ID where available; refresh 30/minute/IP before
  validation plus 30/minute/session after validation; account mutations
  10/minute/user+IP. These are abuse-control defaults, not a new product role.
- Document every auth route in OpenAPI, including Bearer scheme, refresh cookie
  and CSRF header. Keep schema/docs public in local development; restrict
  production schema/docs to configured internal/staff access rather than
  exposing it by default.

### 4. Ownership/header and schema compatibility

- Interpret `Owning apps: users, common` as `users` owning models, services,
  endpoints and auth orchestration; `common` may provide only reusable CSRF,
  error-envelope and request-context primitives.
- Preserve applied migration history. Add forward migrations for RefreshSession,
  replay ledger, username max length/constraints and required indexes; do not
  rewrite `0001_initial`.

## Rejected alternatives

- Client-provided nonce or switching to current Telegram OIDC: not the accepted
  legacy Login Widget contract for this feature.
- Replay key based only on `telegram_id`, `auth_date` or client IP: does not
  represent the full signed payload and can reject legitimate payloads or be
  bypassed from another IP.
- Redis-only replay protection: cache eviction/restart breaks the invariant.
- Raw payload, bot token, refresh JWT or access JWT persistence/logging.
- Users importing learning or a new generic repository/event/queue layer.
- Tombstone/soft-delete identity retention: retention is not accepted and would
  prevent the least-retention re-registration behavior.
- Special 404 or idempotent DELETE path after hard deletion: requires a
  tombstone or authentication bypass; stateless stale-token 401 is safer and
  aligns the existing auth error table.
- Silent framework defaults or password-example values for JWT, cookie, CSRF,
  freshness and throttles without recording the baseline.

## Residual risk

- Replay ledger growth has no MVP background cleanup; any future cleanup must
  retain replay safety and be separately reviewed.
- A freshly verified login after deletion intentionally starts a new account;
  clients must not assume account restoration.
- Learning spec 003 must implement the stated User FK cascade contract before
  its models are shipped; feature 001 does not import that app.
- Production must provide one first-party origin, a dedicated JWT key,
  configured CORS/CSRF trusted origins and shared Redis throttling.
- Numeric freshness and throttle defaults are conservative implementation
  baselines and can be tuned only through a security-reviewed change.

## State transition and validation/rollback consequence

After this record is written and the feature contract/plan reflect it, the
manager may transition `SPEC_REVIEW` → `READY_FOR_IMPLEMENTATION` and create
`feature/001-telegram-auth-account`. Implementation must prove replay,
transaction, deletion, CSRF, throttling, cookie and OpenAPI behavior with
focused tests and the full AGENTS validation suite. If any source conflict,
security invariant or migration compatibility issue appears, stop the affected
change, record the evidence and return `BLOCKED`; do not weaken the contract.
Applied migrations are forward-only. A failed implementation can be reverted
on the unpushed feature branch before release, but committed migrations are
never rewritten.

## Final quorum verdict

- Qwen spec-reviewer: `READY` after round 3; no substantive dissent.
- Luna watchdog: `READY` after round 3; no source conflict remains.
- DeepSeek architect: `READY` after round 3; conditional only on this record
  and the explicit feature-contract amendment, now satisfied by this record.
