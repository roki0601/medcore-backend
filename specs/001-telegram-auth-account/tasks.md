# Tasks: Telegram auth and user account

**Input**: Design documents from `specs/001-telegram-auth-account/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`,
`contracts/auth-api.md`, `quickstart.md`, and the accepted quorum decision in
`.omp/decisions/`.

**Tests**: Required by the feature specification and project rules. Write each
story's behavior tests before its implementation and keep them deterministic;
never use real Telegram or production secrets.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add the approved auth dependency and runtime configuration.

- [X] T001 Add `djangorestframework-simplejwt` to `pyproject.toml` and update `uv.lock` with `uv add`.
- [X] T002 Configure `JWT_SIGNING_KEY`, Telegram bot token, JWT lifetimes, cookie settings, CORS/CSRF origins and Redis-backed DRF throttling in `config/settings/base.py`, `config/settings/local.py`, `config/settings/production.py` and `.env.example`.
- [X] T003 Configure project REST authentication, permission defaults, throttle classes and SimpleJWT validation settings in `config/settings/base.py` without changing public health behavior.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Establish shared API errors, CSRF behavior and durable auth schema.

**Critical**: User-story work depends on this phase.

- [X] T004 Implement the stable `{code, detail, fields}` DRF exception envelope and CSRF failure response in `apps/common/exceptions.py` and `apps/common/views.py`, then wire `EXCEPTION_HANDLER` and `CSRF_FAILURE_VIEW` in `config/settings/base.py`.
- [X] T005 Add forward User validation for NFKC/trim/lowercase username, 3–30 characters and the documented Latin/digit/dot/underscore/hyphen alphabet in `apps/users/models.py` while preserving existing applied migration history.
- [X] T006 Add `RefreshSession` and `TelegramLoginReplay` models, indexes, unique constraints and admin-safe representations in `apps/users/models.py` and `apps/users/admin.py`.
- [X] T007 Generate and inspect the forward PostgreSQL migration for username length and auth tables in `apps/users/migrations/0002_*.py`; preserve existing rows without truncation and fail on incompatible data.
- [X] T008 Add shared auth test fixtures and deterministic signed legacy Telegram payload builders in `apps/users/tests/conftest.py` and `apps/users/tests/helpers.py` without storing secrets.

**Checkpoint**: Errors, CSRF, settings and forward schema are ready for user
stories.

---

## Phase 3: User Story 1 - Telegram login (Priority: P1) MVP

**Goal**: Verify a legacy Telegram Login Widget payload, reject stale/invalid/
replayed requests, create or find exactly one User by `telegram_id`, and issue
access plus refresh credentials.

**Independent Test**: Signed valid payloads create/find one User and set the
access response plus HttpOnly refresh cookie; invalid signature, missing claims,
stale/future and exact replay payloads return stable 401 errors without writes.

### Tests for User Story 1

- [X] T009 Add service tests for canonical Telegram HMAC verification, missing claims, invalid signature, stale/future `auth_date`, replay digest uniqueness and safe logging expectations in `apps/users/tests/test_services.py`.
- [X] T010 Add API tests for first login, repeat fresh login, concurrent first-login uniqueness, generated fallback username and inactive-user rejection in `apps/users/tests/test_api.py`.

### Implementation for User Story 1

- [X] T011 [US1] Implement legacy Telegram payload serializer and verification service with sorted data-check string, HMAC comparison, 86400-second freshness and 60-second future skew in `apps/users/serializers.py` and `apps/users/services.py`.
- [X] T012 [US1] Implement atomic replay-ledger consume, canonical `telegram_id` User lookup/create, unique application-username generation and RefreshSession/JWT issuance in `apps/users/services.py`.
- [X] T013 [US1] Implement Telegram login request/response serializers and the CSRF-protected `POST /api/v1/auth/telegram/` endpoint with stable errors in `apps/users/serializers.py`, `apps/users/views.py` and `apps/users/urls.py`.
- [X] T014 [US1] Add OpenAPI request/response/error schemas and refresh-cookie/CSRF descriptions for Telegram login in `apps/users/views.py` and `config/urls.py`.

**Checkpoint**: User Story 1 is independently usable and proves the primary
MVP authentication path.

---

## Phase 4: User Story 2 - Account username (Priority: P1)

**Goal**: Read the current account and change only the mutable application
username under normalization, validation and case-insensitive uniqueness rules.

**Independent Test**: Authenticated PATCH with a valid username updates the
profile; invalid values and collisions return documented errors and never change
Telegram identity or the previous username.

### Tests for User Story 2

- [X] T015 [US2] Add API tests for profile read, username normalization, length/alphabet boundaries, unknown fields, collision and concurrent update conflict in `apps/users/tests/test_api.py`.

### Implementation for User Story 2

- [X] T016 [US2] Implement account summary and username-update serializers that expose `has_telegram` but never expose raw Telegram identity or secrets in `apps/users/serializers.py`.
- [X] T017 [US2] Implement transactional username update service with narrow unique-race handling and `USERNAME_TAKEN`/`VALIDATION_ERROR` mapping in `apps/users/services.py`.
- [X] T018 [US2] Implement Bearer-protected `GET/PATCH /api/v1/auth/me/` views and URL wiring with OpenAPI schemas in `apps/users/views.py` and `apps/users/urls.py`.

**Checkpoint**: User Story 2 preserves the User's Telegram identity while
supporting a mutable application username.

---

## Phase 5: User Story 3 - Session lifecycle (Priority: P1)

**Goal**: Authenticate Bearer requests and implement non-rotating refresh,
current logout, logout-all, CSRF, cookie clearing and abuse throttling.

**Independent Test**: A valid refresh cookie yields a new access token without
rotation; revoked/expired/inactive/auth-version-mismatched sessions fail;
logout and logout-all revoke the expected session set; cookie state changes
require CSRF and throttled endpoints return the stable 429 envelope.

### Tests for User Story 3

- [X] T019 [US3] Add authentication tests for valid/expired Bearer JWT, inactive User, invalid issuer/audience/type, auth-version mismatch and missing credentials in `apps/users/tests/test_authentication.py`.
- [X] T020 [US3] Add API tests for refresh success/non-rotation, revoked refresh, current logout idempotency, logout-all, refresh/logout race and cookie attributes in `apps/users/tests/test_api.py`.
- [X] T021 [US3] Add CSRF and throttle tests for login, refresh, logout and account mutation scopes in `apps/users/tests/test_api.py`.

### Implementation for User Story 3

- [X] T022 [US3] Implement SimpleJWT Bearer authentication with issuer/audience/type, active-user, auth-version and safe error checks in `apps/users/authentication.py`.
- [X] T023 [US3] Implement locked RefreshSession validation/update, non-rotating access refresh, current-session revocation and logout-all service operations in `apps/users/services.py`.
- [X] T024 [US3] Implement CSRF bootstrap, refresh, logout and logout-all endpoints with exact cookie clearing, stable errors and OpenAPI security metadata in `apps/common/views.py`, `apps/users/views.py` and `apps/users/urls.py`.
- [X] T025 [US3] Implement scoped Redis-backed authentication throttles and attach them to Telegram login, refresh and account mutation endpoints in `apps/users/throttles.py` and `apps/users/views.py`.

**Checkpoint**: User Story 3 proves the complete revocable session lifecycle.

---

## Phase 6: User Story 4 - Self-delete (Priority: P2)

**Goal**: Require explicit confirmation, revoke sessions and physically delete
only the authenticated User; future learning-owned User FKs cascade without a
users-to-learning import.

**Independent Test**: Wrong/missing confirmation changes nothing; valid DELETE
returns 204 and removes User/session state; stale credentials return 401 and a
fresh Telegram payload creates a new empty account rather than restoring data.

### Tests for User Story 4

- [X] T026 Add deletion tests for confirmation validation, transactional session revocation, hard deletion, stale-token 401 no-op and repeated request; verify future learning-owned User-FK cascade remains in the owning app without a users-to-learning import because `apps/learning/models.py` is not yet implemented.

### Implementation for User Story 4

- [X] T027 Implement locked transactional `delete_account` service that revokes RefreshSession rows before deleting User in `apps/users/services.py`.
- [X] T028 Implement confirmation serializer and Bearer-protected `DELETE /api/v1/auth/me/` endpoint with the documented 204/401 behavior and OpenAPI schema in `apps/users/serializers.py`, `apps/users/views.py` and `apps/users/urls.py`.

**Checkpoint**: User Story 4 deletes account state without retaining a
Telegram tombstone or widening users' domain dependencies.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Close documentation, OpenAPI deployment policy and project-level
verification after all stories pass.

- [X] T029 Update `config/urls.py` and production settings so schema/docs are public only in local development and restricted to configured internal/staff access in production.
- [X] T030 Verify Django admin never exposes replay payloads, JWTs, refresh cookies or bot secrets; update `apps/users/admin.py` and safe technical logging in `apps/users/services.py` if needed.
- [X] T031 Run `specs/001-telegram-auth-account/quickstart.md` smoke sequence and verify generated OpenAPI contains every auth endpoint and security requirement.
- [X] T032 Run the exact AGENTS.md project checks and record command/output evidence in the completion report.

---

## Dependencies & Execution Order

### Phase Dependencies

- Setup (Phase 1) precedes Foundational (Phase 2).
- Foundational (Phase 2) blocks all user stories.
- User stories execute sequentially in priority order in this checkout because
  they share `apps/users/services.py`, serializers, views, URLs and migrations.
- Polish runs only after all four stories and focused tests pass.

### User Story Dependencies

- **US1 (P1)** starts after Foundational and establishes Telegram login/session
  creation.
- **US2 (P1)** depends on US1's User summary and Bearer authentication.
- **US3 (P1)** depends on US1's RefreshSession/JWT issuance and US2's protected
  account routing.
- **US4 (P2)** depends on US3's authentication and session revocation service.

### Within Each User Story

Tests are written first and must fail before implementation. Models/schema come
before services, services before endpoints, and OpenAPI follows the actual
endpoint contract. Each story is smoke-checked before the next story begins.

### Parallel Opportunities

- T001–T003 are independent configuration/dependency tasks.
- T009–T010 can be authored in parallel because they target distinct test
  concerns, but implementation remains sequential after both are present.
- T019–T021 can be authored in parallel before US3 implementation.
- No implementation writers should edit the shared service/migration boundary
  concurrently.

## Implementation Strategy

1. Complete setup and foundational schema/error behavior.
2. Deliver US1 as the smallest usable MVP and run its focused checks.
3. Add profile username management, then session lifecycle and deletion.
4. Run quickstart and all project checks only after the final coherent diff.
5. Stop and record `BLOCKED` if any source conflict, security invariant or
   forward migration compatibility issue cannot be resolved from the accepted
   contract; never weaken a test to pass.
