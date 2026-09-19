# Tasks: Content catalog and Topic access

**Input**: Design documents from `specs/002-content-catalog-access/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`,
`contracts/content-api.md`, `quickstart.md`, and the accepted delegated review
in `.omp/decisions/2026-09-19-002-content-catalog-access-quorum.md`.

**Tests**: Required by the feature specification and project rules. Write the
story behavior tests before the corresponding implementation and keep them
deterministic; never store real secrets.

## Phase 1: Setup (Shared Infrastructure)

- [X] T001 Add the `MediaFile` metadata model, constraints and `media.0001_initial` migration in `apps/media/models.py` and `apps/media/migrations/`.
- [X] T002 Add the public entitlement boundary `has_paid_content_entitlement` in `apps/subscriptions/policy.py` documenting the deny-by-default MVP result, with tests in `apps/subscriptions/tests/test_policy.py`.
- [X] T003 Add the standard page-number pagination primitive in `apps/common/pagination.py` and wire `DEFAULT_PAGINATION_CLASS` plus the `catalog`, `content_read` and `search` throttle rates in `config/settings/base.py`.

---

## Phase 2: Foundational (Blocking Prerequisites)

- [X] T004 Add `Subject`, `Section`, `Topic`, `ContentBlockType`, `ContentBlock` and `Source` models with `TextChoices`, DB `CheckConstraint`s, `(parent, position)` and slug uniqueness, and the documented FK deletion matrix in `apps/content/models.py`.
- [X] T005 Generate and inspect `apps/content/migrations/0001_initial.py` depending on `media.0001`, plus `0002_seed_content_block_types.py` as an idempotent `ContentBlockType` seed.
- [X] T006 Add the raw-HTML/unsafe-URL validator for `markdown_body` in `apps/content/validators.py` and attach it to the model field so both Admin and serializers run it.
- [X] T007 Add content test fixtures/conftest helpers in `apps/content/tests/conftest.py` (subjects/sections/topics/blocks, staff editor/admin users, media rows) without secrets.

**Checkpoint**: Schema, validation and fixtures are ready for stories.

---

## Phase 3: User Story 1 - Catalog discovery (P1)

**Goal**: Anonymous clients see the published catalog with access metadata and no
protected body or storage secret.

- [X] T008 [US1] Implement slug generation with deterministic `-N` suffix and locked position assignment services in `apps/content/services.py`.
- [X] T009 [US1] Implement published-only catalog selectors with `has_demo_preview` annotation and parent filters in `apps/content/selectors.py`.
- [X] T010 [US1] Implement catalog serializers (subject, section, topic, source) that never expose body or `storage_key` in `apps/content/serializers.py`.
- [X] T011 [US1] Implement `GET /api/v1/subjects/`, `/subjects/{id}/`, `/sections/{id}/`, `/topics/`, `/topics/{id}/` as thin `AllowAny` views with OpenAPI metadata, throttles and URL wiring in `apps/content/views.py`, `apps/content/urls.py` and `config/urls.py`.
- [X] T012 [US1] Add model/constraint/selector/API tests for catalog visibility, draft hiding, access metadata, pagination, 404 and 422 filter errors in `apps/content/tests/test_models.py`, `test_selectors.py` and `test_api.py`.

---

## Phase 4: User Story 2 - Topic reading (P1)

**Goal**: Actors read the ordered published theory they are entitled to.

- [X] T013 [US2] Implement `apps/content/access.py` composing `access_level`, authentication state, published demo preview and `subscriptions.policy` into a ready access decision.
- [X] T014 [US2] Implement the access-aware topic content selector returning ordered published blocks with sources in `apps/content/selectors.py`.
- [X] T015 [US2] Implement the content serializers exposing body only for allowed blocks, media reference without storage key, and sources in `apps/content/serializers.py`.
- [X] T016 [US2] Implement `GET /api/v1/topics/{id}/content/` with the documented 200/401/403/404 decisions and OpenAPI metadata in `apps/content/views.py` and `apps/content/urls.py`.
- [X] T017 [US2] Add access-matrix tests: demo full, free authenticated, anonymous preview subset, anonymous no-preview 401, paid without entitlement 403, paid entitlement allow via policy override, draft 404, ordering and no body leakage in `apps/content/tests/test_access.py` and `test_api.py`.

---

## Phase 5: User Story 3 - Content authoring (P1)

**Goal**: Editors create the hierarchy and publish blocks deterministically
through the CMS surface.

- [X] T018 [US3] Implement save/publish/delete services with transaction boundaries, publish precondition checks and server-assigned `published_at` in `apps/content/services.py`.
- [X] T019 [US3] Register content models in Django Admin with a permission hook requiring staff plus `role in {editor, admin}` and service-backed saves in `apps/content/admin.py`.
- [X] T020 [US3] Add service/admin tests for slug and position determinism, duplicate position 409, publish preconditions 409, raw-HTML rejection 422, editor/admin access and Topic cascade with sibling preservation in `apps/content/tests/test_services.py` and `test_api.py`.
- [X] T021 [US3] Add a concurrency test proving locked deterministic assignment under one parent produces no duplicate positions or nondeterministic ordering in `apps/content/tests/test_services.py`.

---

## Phase 6: User Story 4 - Source attribution (P2)

- [X] T022 [US4] Implement Source M2M attach/detach in services and include sources in Topic/content responses in `apps/content/services.py` and `apps/content/serializers.py`.
- [X] T023 [US4] Add source attach/detach/delete tests proving relations are removed without deleting Topic/ContentBlock in `apps/content/tests/test_services.py` and `test_api.py`.

---

## Phase 7: Polish & Cross-Cutting

- [X] T024 Implement `GET /api/v1/search/` with title search, subject/section filters, grouping and pagination, plus 422 invalid-filter handling in `apps/content/selectors.py`, `apps/content/views.py` and `apps/content/urls.py`.
- [X] T025 Add search tests for case-insensitivity, filters, pagination, published-only topics and no body leakage in `apps/content/tests/test_api.py`.
- [X] T026 Verify OpenAPI contains the six content paths with permissions and error responses; verify throttled requests return 429 `THROTTLED` in `apps/content/tests/test_api.py`.
- [X] T027 Run `specs/002-content-catalog-access/quickstart.md` smoke sequence against live PostgreSQL/Redis and record evidence.
- [X] T028 Run the exact AGENTS.md project checks and record command/output evidence in the completion report.

---

## Dependencies & Execution Order

- Phase 1 precedes Phase 2; `media.0001` precedes `content.0001`.
- Phase 2 blocks all stories.
- US1 → US2 → US3 → US4 execute sequentially in this checkout because they share
  `apps/content/services.py`, `selectors.py`, serializers, views and URLs.
- Polish runs after all stories pass.
- Only one implementation writer edits the shared content boundary at a time.

## Implementation Strategy

1. Media/policy/pagination primitives and content schema first.
2. Deliver US1 (safe catalog) as the smallest usable slice, then US2 access
   composition, US3 authoring and US4 sources.
3. Run the quickstart and the full project checks only after the final coherent
   diff.
4. Stop and record `BLOCKED` if a source conflict or migration-compatibility
   issue appears; never weaken a test to pass.