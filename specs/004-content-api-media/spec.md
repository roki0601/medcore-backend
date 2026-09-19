# Spec: Synchronous Content API and protected media

Status: Approved for implementation (delegated review
`.omp/decisions/2026-09-19-004-content-api-media-review.md`)

Owning apps: content, media, common

Risk: High

Related architecture: docs/architecture/target-architecture.md,
docs/architecture/conventions.md, docs/architecture/domain-model.md

Related decisions: medcore-docs/decisions/0008-mvp-auth-content-and-integration-contract.md,
medcore-docs/decisions/0004-mvp-decision-register.md,
medcore-docs/decisions/0006-anonymous-demo-content.md,
medcore-docs/decisions/0007-content-access-model.md,
`.omp/decisions/2026-09-19-002-content-catalog-access-quorum.md`

## Goal

Дать внешнему отправителю простой API для записи MedCore-контента без
фиксированного формата файла, очереди или фонового import job. Отдельно
обеспечить хранение media вне PostgreSQL и безопасную выдачу private/paid
файлов через временные signed URLs.

## Scope

- Один отдельный integration key для content API.
- Синхронные REST CRUD endpoints для content entities, включая Quiz aggregate с
  nested questions/answers.
- Валидация обычными API-сериализаторами и domain services.
- Optional external_id для повторяемых upsert-запросов.
- Явное удаление Topic aggregate без затрагивания соседних объектов.
- Media/File metadata boundary.
- Image upload/reference flow через provider-neutral object-storage adapter с
  local backend для dev/test и S3-compatible backend для deployment.
- Backend access check перед выдачей private/paid signed URL.
- Safe integration logs, throttling and OpenAPI.

## Out of scope

- Единый формат import-файла.
- ImportJob, Celery, Redis queue и worker.
- Автоматическое удаление объектов, отсутствующих в следующем payload, включая
  nested questions/answers.
- Bulk endpoints на первом этапе.
- Удаление отдельного Question/Answer: children quiz только создаются и
  обновляются (immutable-content policy, см. Business rules).
- Произвольное сохранение неизвестного JSON.
- Payment provider и subscription lifecycle.
- Конкретный object-storage provider, его credentials и object-storage сервис в
  `compose.yaml`.
- Video/audio processing.

## Actors

| Actor | Разрешённые действия |
|---|---|
| integration client | synchronous content/media CRUD with integration key |
| editor | CMS content CRUD according to role policy |
| admin | full content/media administration |
| user | read content and receive media URL after normal access check |
| anonymous | read public/demo content and public media only |

## User scenarios

### User Story 1 — direct content write (P1)

Внешний клиент преобразует свои данные в несколько API-запросов и создаёт или
обновляет контент.

Acceptance scenarios:

1. Given valid integration key and valid Subject payload, when client sends POST,
   then backend creates a Subject synchronously and returns its representation.
2. Given existing external_id within the integration namespace, when client sends
   an update request, then backend updates the same entity rather than creating a
   duplicate.
3. Given invalid relation or content payload, when client sends request, then
   only that request fails with stable validation error and no partial entity is
   committed.

### User Story 2 — explicit deletion (P1)

Внешний клиент или admin удаляет конкретную тему.

Acceptance scenarios:

1. Given a Topic ID, when authorized client sends DELETE, then the Topic and its
   owned blocks/cards/quizzes/questions are deleted.
2. Given sibling Topics, Sections or Subjects, when a Topic is deleted, then
   sibling aggregates remain unchanged.
3. Given repeated DELETE of the same Topic, then response follows idempotent
   delete convention without recreating or deleting other objects.

### User Story 3 — protected media (P1)

Пользователь получает ссылку на картинку только после backend access check.

Acceptance scenarios:

1. Given public/demo media, when an allowed client reads content, then it receives
   a usable public or signed URL according to media visibility policy.
2. Given paid/private media and no entitlement, when client requests content, then
   backend returns access error and no storage URL.
3. Given paid/private media and valid entitlement, when client requests content,
   then backend returns signed URL with short expiry.

## Entities

- Integration credential: one configured secret used only by external content
  clients.
- Content entities: Subject, Section, Topic, ContentBlock, Flashcard, Quiz,
  QuizQuestion, QuizAnswer and Source, owned by content.
- Quiz owns its QuizQuestion and QuizAnswer children as one aggregate; they are
  created and updated only through the Quiz write payload and are never deleted
  individually.
- MediaFile: metadata and object-storage reference, owned by media.

## Business rules

1. Integration key is separate from user JWT and cannot authenticate frontend
   users.
2. The integration client is allowed only content and media operations.
3. Unknown JSON fields or unknown entity types are rejected, not persisted.
4. External client chooses its own source format and request ordering.
5. Backend validates every request and returns created/updated representation
   synchronously.
6. external_id is optional but, when supplied, is stable within the integration
   namespace and supports idempotent upsert. An established external_id is
   immutable: it cannot be changed or cleared through PATCH.
7. No automatic deletion is inferred from an object missing in a later request.
   This includes nested quiz children: an omitted question or answer is never
   deleted.
8. A delete operation must name its exact target.
9. Topic deletion cascades only to children owned by that Topic.
10. Content API cannot read or mutate User, RefreshSession, progress, attempts,
    roles or Subscription internals.
11. Media binary content is not stored in PostgreSQL.
12. Storage key and provider credentials are never returned to clients.
13. Private/protected media URL generation requires successful Topic access
    policy; public media may be signed for anonymous actors because it carries no
    access restriction.
14. Signed URL TTL is 10 minutes by default and is never persisted as permanent
    content data.
15. The Quiz aggregate is written in one transaction: questions and answers are
    upserted by an optional `id`, items without `id` are created, and existing
    child IDs stay stable across updates.
16. A Quiz must keep at least one question; each question must keep at least two
    answers and at least one correct answer. A question may have several correct
    answers.
17. A Topic may contain zero or more quizzes; a Flashcard belongs to exactly one
    Topic.
18. Deleting a MediaFile that a published content block references is rejected;
    the caller must detach the reference first (repair workflow).
19. Authorization for a protected media URL is evaluated before any storage call;
    object metadata is verified before a URL is issued.
20. An upload is usable only after its size (and checksum when supplied) matches
    the declared metadata.
21. The integration key is denied entirely when the configured secret is absent.

## Invariants

- Integration key is required on every integration request and absent from logs.
- external_id uniqueness is scoped to the configured integration namespace and
  entity type.
- One request commits either the complete entity mutation or nothing.
- Topic deletion cannot affect a sibling aggregate.
- A signed URL cannot be issued without an access decision.
- Storage metadata and referenced content relation cannot expose credentials.
- A published content block keeps its media reference; media deletion is refused
  while such a reference exists.
- Quiz child IDs are never regenerated or deleted by the content API.
- Capability tokens for the controlled upload/access contract never contain the
  storage key, are bound to one operation, media id, HTTP method and expiry, and
  are never logged.

## Data model

### Integration configuration

For MVP the key is configured outside the database:

- environment secret MEDCORE_CONTENT_API_KEY;
- key comparison is constant-time;
- key is replaceable on deployment restart;
- raw value is never persisted or logged.

Multiple database-managed keys and scopes are deferred.

### External identity

Content entities may carry optional external_id. It is not a user-facing URL
identifier and does not replace numeric database IDs. It is nullable and unique
per model (one configured integration namespace, one identity per entity type);
an established value is immutable.

### Content entities added by this feature

- Flashcard: topic (required, CASCADE), question, answer, position,
  external_id, timestamps.
- Quiz: topic (required, CASCADE), title, description, position, external_id,
  timestamps.
- QuizQuestion: quiz (required, CASCADE), text, position.
- QuizAnswer: question (required, CASCADE), text, is_correct, position.
- Source gains the accepted optional M2M relations to Flashcard and
  QuizQuestion in addition to Topic and ContentBlock.

Ordering is `(position, id)` with a unique `(parent, position)` constraint on
every child relation. No shuffle or status field is persisted; presentation
order is a client concern and visibility follows the Topic. Source M2M relations
are set through the Source write payload and never delete content.

### MediaFile

- storage_key: required opaque provider key, generated server-side, never
  serialized.
- original_name: optional safe display name.
- mime_type: required allow-listed MIME.
- size_bytes: required positive integer under configured limit.
- checksum: optional integrity value.
- visibility: public or protected.
- created_at, updated_at: UTC timestamps.

Content blocks reference MediaFile by foreign key. MediaFile does not own Topic
access semantics; the referenced content and access policy do.

### Media storage configuration

- `MEDIA_STORAGE_BACKEND`: `local` (default) or `s3`.
- `local` stores objects under `MEDIA_STORAGE_ROOT` and issues capability URLs to
  the controlled endpoints `PUT /api/v1/media/upload/{token}/` and
  `GET /api/v1/media/file/{token}/`. It is a dev/test backend; a Django system
  check fails when it is selected with `DEBUG=False`.
- `s3` is provider-neutral S3-compatible (MinIO, AWS S3 or any S3 API) with
  endpoint, bucket, region and credentials from the environment, and returns
  presigned upload/access URLs. Its SDK is an optional dependency group; the
  concrete provider remains a deployment decision.
- `MEDIA_UPLOAD_URL_TTL` and `MEDIA_ACCESS_URL_TTL` default to 600 seconds;
  `MEDIA_ALLOWED_MIME_TYPES` is `image/png`, `image/jpeg`, `image/webp`,
  `image/gif`; `MEDIA_MAX_UPLOAD_BYTES` defaults to 5 MiB.
- `apps/media` never imports `apps/content`. The two content-owned decisions it
  needs (media access decision, media deletion guard) are provided through
  fail-closed settings entries resolved with `import_string`:
  `MEDIA_ACCESS_POLICY_PROVIDER` and `MEDIA_DELETE_GUARD_PROVIDER`, both pointing
  at `apps.content.media_policy`. A missing provider denies protected media and
  refuses media deletion.

## API

All URLs use /api/v1/ and trailing slashes.

### Integration authentication

Header:

    X-MedCore-Integration-Key: <secret>

This header is accepted only by explicitly marked content/media endpoints. User
JWT remains the authentication mechanism for normal user APIs, and user-facing
views never read this header.

- The integration authenticator runs before the JWT authenticator on marked
  routes.
- A header that is present but wrong or empty fails immediately with 401
  `INTEGRATION_KEY_INVALID`, even when a valid user JWT is also supplied.
- An absent header falls through to the normal JWT path.
- An unset `MEDCORE_CONTENT_API_KEY` denies every integration request.
- The principal is not a `User`: it has no role, no Django user attributes and
  cannot satisfy `IsAuthenticated`. Content authoring routes allow
  `editor`/`admin` JWT or the integration principal; `access-url` rejects the
  integration principal with 403 `INTEGRATION_SCOPE_FORBIDDEN`.

### Content CRUD

Integration/editor/admin endpoints:

- GET, POST /api/v1/content/subjects/
- GET, PATCH, DELETE /api/v1/content/subjects/{id}/
- GET, POST /api/v1/content/sections/
- GET, PATCH, DELETE /api/v1/content/sections/{id}/
- GET, POST /api/v1/content/topics/
- GET, PATCH, DELETE /api/v1/content/topics/{id}/
- GET, POST /api/v1/content/blocks/
- GET, PATCH, DELETE /api/v1/content/blocks/{id}/
- GET, POST /api/v1/content/flashcards/
- GET, PATCH, DELETE /api/v1/content/flashcards/{id}/
- GET, POST /api/v1/content/quizzes/
- GET, PATCH, DELETE /api/v1/content/quizzes/{id}/
- GET, POST /api/v1/content/sources/
- GET, PATCH, DELETE /api/v1/content/sources/{id}/

Request and response schemas are entity-specific. POST returns 201 for a new
entity. PATCH returns 200. DELETE returns 204 for the first delete; a repeated
DELETE returns 404 `RESOURCE_NOT_FOUND` and never recreates or deletes another
object.

- Unknown top-level JSON fields are rejected with 422 `VALIDATION_ERROR`; DRF's
  default ignore-unknown-fields behavior is overridden deliberately.
- `POST` with an `external_id` that already exists updates that entity and
  returns 200; otherwise it creates and returns 201. `PATCH` that changes or
  clears an established `external_id` returns 409 `EXTERNAL_ID_CONFLICT`.
- Quiz write payloads nest `questions: [{id?, text, position?, answers:
  [{id?, text, is_correct, position?}]}]`. Items with `id` are updated in place
  (ID preserved) and must belong to that quiz, items without `id` are created,
  omitted items are left untouched, and no child is ever deleted. The quiz detail
  response returns the nested questions and answers with their IDs; the list
  response returns quiz scalar fields only.
- Block write payloads accept `block_type` by key, `media` by id, `status`,
  `is_demo_preview`, `markdown_body` and `caption`, and reuse the spec 002
  publish preconditions and `published_at` assignment.
- Source write payloads accept `topic_ids`, `block_ids`, `flashcard_ids` and
  `question_ids` as set semantics inside one transaction; deleting a Source
  removes links only.

### Media

- POST /api/v1/media/
- GET /api/v1/media/{id}/
- DELETE /api/v1/media/{id}/
- GET /api/v1/media/{id}/upload-url/
- GET /api/v1/media/{id}/access-url/
- PUT /api/v1/media/upload/{token}/ (controlled upload contract of the local
  backend; 404 when the configured backend does not provide it)
- GET /api/v1/media/file/{token}/ (capability download URL of the local backend)

`POST /api/v1/media/` creates metadata only and never returns `storage_key`.
`GET /api/v1/media/{id}/upload-url/` returns a provider-neutral
`{upload_url, method, expires_at}`; the adapter returns a presigned URL or the
controlled upload contract. The concrete provider is selected at deployment
time.

`access-url` is `AllowAny`:

| visibility | actor | result |
|---|---|---|
| `public` | anonymous or authenticated | 200 signed/public URL |
| `protected` | anonymous, no readable published reference | 401 `AUTHENTICATION_REQUIRED` |
| `protected` | anonymous, readable published demo/preview reference | 200 signed URL |
| `protected` | authenticated with Topic access to a published reference | 200 signed URL |
| `protected` | authenticated without access | 403 `MEDIA_ACCESS_DENIED` |
| any | integration principal | 403 `INTEGRATION_SCOPE_FORBIDDEN` |
| any | object missing or metadata mismatch | 422 `MEDIA_INVALID` |

Authorization is evaluated before any storage call, so the endpoint never
becomes an object-existence oracle. `DELETE /api/v1/media/{id}/` returns 409
`CONTENT_CONFLICT` while a published content block references the file; the
repair path is detaching the reference first. Integration/admin may inspect
metadata but never receive a permanent public URL for protected media.

### Pagination and errors

List endpoints use standard DRF page-number pagination with default page size 20
and maximum page size 100.

Errors use code, detail and optional fields:

    {
      "code": "INTEGRATION_KEY_INVALID",
      "detail": "Integration credentials are invalid.",
      "fields": {}
    }

## Permissions

| Operation | anonymous | user | editor | admin | integration |
|---|---:|---:|---:|---:|---:|
| public content read | allow | allow | allow | allow | allow with key |
| content write | deny | deny | allow | allow | allow with key |
| Topic delete | deny | deny | CMS policy | allow | allow with key |
| media metadata write | deny | deny | CMS policy | allow | allow with key |
| public media URL | allow | allow | allow | allow | metadata only |
| protected media URL | access policy | own access | user access policy | user access policy | metadata only |
| users/progress/subscriptions | deny | deny | own only where applicable | separate admin APIs | deny |

Integration key does not grant admin role and cannot be used for user-facing
paid-access bypass. Editor/admin role never bypasses user-facing paid access
either; Django Admin is a separate surface gated on staff plus
`role in {editor, admin}`.

## Validation

- Header must be present on integration-only operations.
- Integration key comparison is constant-time; an absent configured secret denies
  every integration request.
- IDs and parent relations must be valid.
- external_id must be stable, non-empty, bounded and unique per entity type.
- Entity-specific serializer validation applies to every request, and unknown
  top-level fields are rejected.
- Delete endpoint accepts only an explicit target ID.
- Quiz aggregate writes require at least one question, at least two answers per
  question and at least one correct answer per question; nested ids must belong
  to the addressed quiz.
- Media MIME and byte size must pass allow-list and configured limit.
- Upload completion must verify object metadata (size, and checksum when
  supplied) before media becomes usable.
- Signed URL generation checks current content access at request time and
  verifies the object before issuing the URL; authorization runs first.

## Errors

| Condition | HTTP | Code |
|---|---:|---|
| missing/invalid integration key | 401 | INTEGRATION_KEY_INVALID |
| missing/expired user authentication on a user-facing route | 401 | AUTHENTICATION_REQUIRED |
| integration key used for forbidden domain | 403 | INTEGRATION_SCOPE_FORBIDDEN |
| invalid payload | 422 | VALIDATION_ERROR |
| invalid relation | 422 | INVALID_RELATION |
| external_id conflict or mutation of an established identity | 409 | EXTERNAL_ID_CONFLICT |
| entity not found | 404 | RESOURCE_NOT_FOUND |
| protected media without access | 403 | MEDIA_ACCESS_DENIED |
| unsupported/too-large media, failed upload verification, missing object | 422 | MEDIA_INVALID |
| media referenced by a published block, duplicate position, quiz aggregate invariant | 409 | CONTENT_CONFLICT |
| publish precondition failure | 409 | INVALID_CONTENT_STATE |
| rate limit | 429 | THROTTLED |

## Edge cases

- Repeating an identical POST with external_id returns/upserts the same entity
  according to the entity contract (200 for the upsert, 201 for the creation).
- Repeating PATCH with the same payload is safe.
- Missing object in a later request does not delete anything, including nested
  quiz children.
- Topic deletion never deletes Section/Subject or sibling Topic; it removes the
  Topic with its blocks, flashcards, quizzes and their questions/answers in one
  transaction.
- Deleting a MediaFile referenced by a published image block is rejected with 409
  `CONTENT_CONFLICT`; the repair workflow is detaching the reference first (an
  image block cannot stay published without media, so the client clears status
  and media in one request), after which the unpublished reference detaches on
  deletion.
- A quiz updated without a question list keeps its questions and answers and
  their IDs unchanged.
- Storage upload succeeds but metadata validation fails: object remains
  inaccessible and cleanup is handled by the media provider policy.
- Signed URL expires: client must request a new URL; old URL is not refreshed.
- Integration key rotation invalidates old key without changing content IDs.
- `MEDIA_STORAGE_BACKEND=local` with `DEBUG=False` fails the project system check
  instead of serving media from a non-object-storage backend.

## Transactions

- Each entity mutation is one database transaction.
- A Topic deletion and owned-child cascade are one transaction.
- external_id lookup and upsert decision occur inside the write transaction.
- The Quiz aggregate (quiz plus questions and answers) is one transaction.
- Media deletion locks the `MediaFile` row, re-checks published references and
  deletes in one transaction; publishing a block that references media takes the
  same row lock so the two operations serialize.
- Storage HTTP calls do not run while holding a database row lock.
- Media metadata becomes published only after upload verification.
- Storage cleanup after a committed delete is an external side effect and must
  be observable; database deletion is not silently rolled back by remote
  provider failure. It runs in `transaction.on_commit`.

## Concurrency

- Database unique constraints protect external_id scope and entity relations.
- Concurrent upserts on the same external_id result in one entity and one stable
  conflict/retry path.
- Concurrent Topic deletes are idempotent and cannot widen their scope.
- Signed URL access is evaluated against current entitlement, not a cached
  frontend decision.
- Concurrent publish and media delete serialize on the `MediaFile` row and can
  never leave a published block without its media.

## Background jobs/events

None for the Content API. No ImportJob, queue or Celery worker is introduced.
Future media cleanup or processing requires a separate accepted decision.

## Security

- Integration key is a secret and is accepted only on marked routes.
- Never log integration key, signed URL query secrets, storage credentials or
  raw sensitive payloads.
- Apply throttling to integration writes, media upload and signed URL issuance.
- Use allow-listed media types and size limits; do not serve executable files.
- Validate and sanitize Markdown/content before publishing.
- Keep protected storage buckets non-public.
- Use HTTPS in production.
- Capability tokens for the controlled upload/access contract are bearer secrets:
  bound to one operation, media id, HTTP method and expiry; never containing the
  storage key; never logged.
- Media authorization runs before any storage call, so the endpoint is not an
  object-existence oracle.

## Risks, compatibility and rollout

- Existing content/media apps are skeletons, so migrations and storage adapter
  are new implementation work.
- A single environment key is simple but limits rotation and audit granularity;
  database-managed keys are deferred.
- Synchronous writes are intentionally simple; large external producers must
  throttle themselves until a separate bulk/async decision is approved.
- Concrete object storage provider remains a deployment decision. Until an
  S3-compatible backend is configured, the local backend is refused outside
  `DEBUG`, so production media upload requires that deployment decision.
- The S3-compatible adapter is exercised with a stubbed client and the local
  backend with a live smoke test; no production bucket is available in this run.
- Quiz children are immutable in identity: content is updated, not removed, which
  is a deliberate narrowing recorded in the decision record.

## Acceptance criteria

1. External client can create/update each supported content entity synchronously
   with one integration key.
2. Unknown payload shapes are rejected and never stored as arbitrary JSON.
3. Repeated external_id writes do not create duplicates, and an established
   external_id cannot be changed or cleared.
4. Explicit Topic deletion affects only the Topic aggregate.
5. No import job, Celery worker or automatic missing-object deletion exists,
   including nested quiz children.
6. Media binary data is outside PostgreSQL.
7. Protected media never yields a URL without backend access approval, and public
   media is readable by anonymous clients.
8. Signed URLs expire and can be reissued after a new access check.
9. OpenAPI, rate limits, stable errors and safe logs cover integration routes.
10. A quiz keeps at least one question with at least two answers and at least one
    correct answer, and question/answer IDs stay stable across updates.
11. Deleting media referenced by a published block is refused until the reference
    is detached, and the check is race-free against concurrent publishing.
12. An integration request with a wrong or empty key fails with 401
    `INTEGRATION_KEY_INVALID` even when a valid user JWT is present, and the key
    never reaches a user-facing route.

## Test scenarios

- Valid/invalid/missing integration key, including alongside a valid JWT.
- Entity create, read, patch, delete and relation validation.
- external_id idempotency, immutability and concurrent upsert.
- Unknown JSON field/type rejection.
- Quiz aggregate upsert with stable child IDs, answer minima and no omission
  deletion.
- Topic cascade deletion and sibling preservation.
- Media MIME/size validation and upload verification.
- Public/demo/private/paid media URL behavior, including anonymous public media.
- Entitlement denial and signed URL expiry.
- Media deletion refusal for a published reference and concurrent
  publish/delete serialization.
- Integration throttling and secret-safe logs.
- Storage provider failure after database commit.

## Dependencies

- Content entities and access contract from spec 002.
- User/auth permissions from spec 001.
- Subscription policy interface for paid media checks.
- Provider-neutral object-storage adapter with a local dev/test backend and an
  S3-compatible backend whose SDK is an optional dependency group; the concrete
  provider remains a deployment decision.
- Self-host reverse proxy and HTTPS configuration.

## Open questions

Closed for this feature by
`.omp/decisions/2026-09-19-004-content-api-media-review.md`:

- Concrete object-storage provider and deployment credentials: remains a
  deployment decision; the adapter interface is the extension point and the
  local backend is refused outside `DEBUG`.
- Final upload completion handshake: provider-neutral; the adapter returns a
  presigned URL or the controlled upload contract, and the declared size (and
  checksum when supplied) must match before the object is usable.
- Whether integration key rotation later becomes database-managed: still
  deferred; one environment key remains the MVP contract.
