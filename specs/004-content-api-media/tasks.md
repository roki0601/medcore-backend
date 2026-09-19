# Tasks: Synchronous content API and protected media

**Input**: Design documents from `specs/004-content-api-media/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`,
`contracts/content-api.md`, `contracts/media-api.md`, `quickstart.md`, and the
accepted delegated review in
`.omp/decisions/2026-09-19-004-content-api-media-review.md`.

**Tests**: Required by the feature specification and project rules. Write the
story behavior tests before the corresponding implementation and keep them
deterministic; never store real secrets.

## Phase 1: Setup (Shared Infrastructure)

- [X] T001 Add `MEDCORE_CONTENT_API_KEY`, the media settings block (`MEDIA_STORAGE_BACKEND`, root, S3 keys, allow-list, limits, TTLs, token salts, policy providers) and the `integration_write`, `media_upload`, `media_access` throttle rates in `config/settings/base.py`, and document every new variable in `.env.example`.
- [X] T002 Add the integration credential primitive in `apps/common/integration.py` (constant-time header authentication, non-User `IntegrationClient` principal, `HasIntegrationKey`, `IsNotIntegrationClient`) and the shared `CONTENT_AUTHOR_ROLES`/`IsContentAuthor` in `apps/common/permissions.py`; reuse the shared role constant in `apps/content/admin.py`; cover the key matrix in `apps/common/tests/test_integration.py`.
- [X] T003 Add the optional `storage-s3` dependency group (`boto3`) plus its dev-group entry in `pyproject.toml` and refresh `uv.lock`.

---

## Phase 2: Foundational (Blocking Prerequisites)

- [X] T004 Add `external_id` to `Subject`, `Section`, `Topic`, `ContentBlock` and `Source`, add `Flashcard`, `Quiz`, `QuizQuestion`, `QuizAnswer` and the `Source.flashcards`/`Source.questions` M2M with the documented constraints and deletion matrix in `apps/content/models.py`, and generate `apps/content/migrations/0003_content_api_entities.py`.
- [X] T005 Add `apps/media/storage.py` with the `StorageAdapter` protocol, `LocalStorageAdapter` (capability-token upload/download URLs, sidecar metadata, `write_object`/`read_object`), `S3StorageAdapter` (presigned URLs, `head_object` verification, optional SDK) and the cached resolver; add the `local`-outside-`DEBUG` system check in `apps/media/checks.py`.
- [X] T006 Add `apps/content/media_policy.py` with `decide_media_access(media, actor)` (published-reference lookup, feature 002 access composition, demo-preview rule, authentication requirement) and `guard_media_deletion(media)` (published-reference rejection with row locks), both callable through the settings providers.
- [X] T007 Add test fixtures for the content CRUD surface (editor/admin/staff users, integration client, catalog with flashcards/quizzes) and for media (media rows, published image block, local storage root) without secrets.

**Checkpoint**: Schema, adapter, policies and fixtures are ready for stories.

---

## Phase 3: User Story 1 - direct content write (P1)

**Goal**: An external client creates and updates every supported content entity
synchronously with one integration key.

- [X] T008 [US1] Implement the write services in `apps/content/services.py`: subject/section/topic/block/flashcard save and delete, Source relation set semantics, `external_id` lookup/upsert with immutability and 409 conflict mapping, and the media-row lock in `publish_content_block`.
- [X] T009 [US1] Implement strict write serializers (unknown-field rejection), the read serializers for the new entities and the nested quiz serializers in `apps/content/serializers.py`.
- [X] T010 [US1] Implement the content CRUD views with the documented permissions, authentication order, 201/200 upsert split, 204/404 delete convention and OpenAPI metadata in `apps/content/views.py`, and wire `/api/v1/content/` routes in `apps/content/urls.py`.
- [X] T011 [US1] Add service and API tests for create/read/patch/delete, relation validation, unknown-field rejection, `external_id` idempotency/immutability/concurrency, editor/admin vs integration vs plain-user access, pagination and 404s in `apps/content/tests/test_services.py` and `apps/content/tests/test_crud_api.py`.

---

## Phase 4: User Story 2 - quiz aggregate and explicit deletion (P1)

**Goal**: Quizzes with questions and answers are authored through one aggregate
write and deletion names its exact target.

- [X] T012 [US2] Implement the quiz aggregate write service (identity-preserving nested upsert, no child deletion, >=1 question, >=2 answers, >=1 correct answer, deterministic positions, one transaction) and its view wiring.
- [X] T013 [US2] Implement Topic deletion through the API reusing the 002 service, with the extended cascade to flashcards/quizzes/questions/answers and the repeated-DELETE convention.
- [X] T014 [US2] Add tests for the aggregate write (stable child IDs, omitted children kept, invariant failures), Topic cascade with sibling preservation and repeated delete in `apps/content/tests/test_services.py` and `apps/content/tests/test_crud_api.py`.

---

## Phase 5: User Story 3 - protected media (P1)

**Goal**: Media is uploaded through the adapter and served only after the backend
access decision.

- [X] T015 [US3] Implement the media services (metadata create/read/delete with the guard and `on_commit` cleanup, upload-url and access-url issuance with authorization before verification, controlled upload acceptance and download) plus serializers, views, URLs and the staff+role admin gate in `apps/media/`.
- [X] T016 [US3] Add tests for MIME/size validation, the upload round trip, verification failures, the access matrix (public, anonymous protected, authenticated protected, integration scope, missing object), capability-token expiry and metadata serialization in `apps/media/tests/`.
- [X] T017 [US3] Add the concurrency test proving publish and media delete serialize on the media row and never leave a published block without its media.

---

## Phase 6: Polish & Cross-Cutting

- [X] T018 Verify OpenAPI contains the fourteen `/content/` and seven `/media/` paths with permissions and error responses, and that throttled requests return 429 `THROTTLED`.
- [X] T019 Run `specs/004-content-api-media/quickstart.md` against live PostgreSQL/Redis with the local storage backend and record evidence.
- [X] T020 Run the exact AGENTS.md project checks and record command/output evidence in the completion report.

---

## Dependencies & Execution Order

- Phase 1 precedes Phase 2; Phase 2 blocks all stories.
- US1 → US2 → US3 execute sequentially because they share `apps/content`
  services, serializers, views and URLs.
- T005/T006 are independent of T008-T014 but land before US3.
- Polish runs after all stories pass.
- Only one implementation writer edits the shared content boundary at a time.

## Implementation Strategy

1. Settings, credential primitive, schema, adapter and policies first.
2. Deliver US1 (integration write) as the smallest usable slice, then US2 (quiz
   aggregate and deletion) and US3 (media upload and protected URLs).
3. Run the quickstart and the full project checks only after the final coherent
   diff.
4. Stop and record `BLOCKED` if a source conflict or migration-compatibility
   issue appears; never weaken a test to pass.
