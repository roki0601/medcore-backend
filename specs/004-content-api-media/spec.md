# Spec: Synchronous Content API and protected media

Status: Draft

Owning apps: content, media, common

Risk: High

Related architecture: docs/architecture/target-architecture.md,
docs/architecture/conventions.md

Related decisions: medcore-docs/decisions/0008-mvp-auth-content-and-integration-contract.md

## Goal

Дать внешнему отправителю простой API для записи MedCore-контента без
фиксированного формата файла, очереди или фонового import job. Отдельно
обеспечить хранение media вне PostgreSQL и безопасную выдачу private/paid
файлов через временные signed URLs.

## Scope

- Один отдельный integration key для content API.
- Синхронные REST CRUD endpoints для content entities.
- Валидация обычными API-сериализаторами и domain services.
- Optional external_id для повторяемых upsert-запросов.
- Явное удаление Topic aggregate без затрагивания соседних объектов.
- Media/File metadata boundary.
- Image upload/reference flow через object-storage adapter.
- Backend access check перед выдачей private/paid signed URL.
- Safe integration logs, throttling and OpenAPI.

## Out of scope

- Единый формат import-файла.
- ImportJob, Celery, Redis queue и worker.
- Автоматическое удаление объектов, отсутствующих в следующем payload.
- Bulk endpoints на первом этапе.
- Произвольное сохранение неизвестного JSON.
- Payment provider и subscription lifecycle.
- Конкретный object-storage provider.
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
  Question, Answer and Source, owned by content.
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
   namespace and supports idempotent upsert.
7. No automatic deletion is inferred from an object missing in a later request.
8. A delete operation must name its exact target.
9. Topic deletion cascades only to children owned by that Topic.
10. Content API cannot read or mutate User, RefreshSession, progress, attempts,
    roles or Subscription internals.
11. Media binary content is not stored in PostgreSQL.
12. Storage key and provider credentials are never returned to clients.
13. Private/paid media URL generation requires successful Topic access policy.
14. Signed URL TTL is 10 minutes by default and is never persisted as permanent
    content data.

## Invariants

- Integration key is required on every integration request and absent from logs.
- external_id uniqueness is scoped to the configured integration namespace and
  entity type.
- One request commits either the complete entity mutation or nothing.
- Topic deletion cannot affect a sibling aggregate.
- A signed URL cannot be issued without an access decision.
- Storage metadata and referenced content relation cannot expose credentials.

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
identifier and does not replace numeric database IDs.

### MediaFile

- storage_key: required opaque provider key.
- original_name: optional safe display name.
- mime_type: required allow-listed MIME.
- size_bytes: required positive integer under configured limit.
- checksum: optional integrity value.
- visibility: public or protected.
- created_at, updated_at: UTC timestamps.

Content blocks reference MediaFile by foreign key. MediaFile does not own Topic
access semantics; the referenced content and access policy do.

## API

All URLs use /api/v1/ and trailing slashes.

### Integration authentication

Header:

    X-MedCore-Integration-Key: <secret>

This header is accepted only by explicitly marked content/media endpoints. User
JWT remains the authentication mechanism for normal user APIs.

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
entity. PATCH returns 200. DELETE returns 204 or the agreed idempotent success
body.

Integration requests may use external_id and source namespace fields where the
entity supports them. They do not accept arbitrary top-level JSON.

### Media

- POST /api/v1/media/
- GET /api/v1/media/{id}/
- DELETE /api/v1/media/{id}/
- GET /api/v1/media/{id}/upload-url/
- GET /api/v1/media/{id}/access-url/

Upload URL response is provider-neutral. The actual storage adapter may return a
presigned upload URL or an equivalent controlled upload contract. The final
provider is selected during implementation planning.

access-url requires normal user authentication and Topic access evaluation for
the content reference. Integration/admin may inspect metadata but must not
receive a permanent public URL for protected media.

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
| protected media URL | access policy | own access | user access policy | user access policy | metadata only |
| users/progress/subscriptions | deny | own only where applicable | own only | separate admin APIs | deny |

Integration key does not grant admin role and cannot be used for user-facing
paid-access bypass.

## Validation

- Header must be present on integration-only operations.
- Integration key comparison is constant-time.
- IDs and parent relations must be valid.
- external_id must be stable, non-empty and bounded when supplied.
- Entity-specific serializer validation applies to every request.
- Delete endpoint accepts only an explicit target ID.
- Media MIME and byte size must pass allow-list and configured limit.
- Upload completion must verify object metadata before media becomes usable.
- Signed URL generation checks current content access at request time.

## Errors

| Condition | HTTP | Code |
|---|---:|---|
| missing/invalid integration key | 401 | INTEGRATION_KEY_INVALID |
| integration key used for forbidden domain | 403 | INTEGRATION_SCOPE_FORBIDDEN |
| invalid payload | 422 | VALIDATION_ERROR |
| invalid relation | 422 | INVALID_RELATION |
| external_id conflict | 409 | EXTERNAL_ID_CONFLICT |
| entity not found | 404 | RESOURCE_NOT_FOUND |
| protected media without access | 403 | MEDIA_ACCESS_DENIED |
| unsupported/too-large media | 422 | MEDIA_INVALID |
| concurrent state conflict | 409 | CONTENT_CONFLICT |
| rate limit | 429 | THROTTLED |

## Edge cases

- Repeating an identical POST with external_id returns/upserts the same entity
  according to the entity contract.
- Repeating PATCH with the same payload is safe.
- Missing object in a later request does not delete anything.
- Topic deletion never deletes Section/Subject or sibling Topic.
- Deleting a MediaFile referenced by a published image block is rejected or
  requires repair workflow before deletion.
- Storage upload succeeds but metadata validation fails: object remains
  inaccessible and cleanup is handled by the media provider policy.
- Signed URL expires: client must request a new URL; old URL is not refreshed.
- Integration key rotation invalidates old key without changing content IDs.

## Transactions

- Each entity mutation is one database transaction.
- A Topic deletion and owned-child cascade are one transaction.
- external_id lookup and upsert decision occur inside the write transaction.
- Storage HTTP calls do not run while holding a database row lock.
- Media metadata becomes published only after upload verification.
- Storage cleanup after a committed delete is an external side effect and must
  be observable; database deletion is not silently rolled back by remote
  provider failure.

## Concurrency

- Database unique constraints protect external_id scope and entity relations.
- Concurrent upserts on the same external_id result in one entity and one stable
  conflict/retry path.
- Concurrent Topic deletes are idempotent and cannot widen their scope.
- Signed URL access is evaluated against current entitlement, not a cached
  frontend decision.

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

## Risks, compatibility and rollout

- Existing content/media apps are skeletons, so migrations and storage adapter
  are new implementation work.
- A single environment key is simple but limits rotation and audit granularity;
  database-managed keys are deferred.
- Synchronous writes are intentionally simple; large external producers must
  throttle themselves until a separate bulk/async decision is approved.
- Concrete object storage provider remains a deployment decision.

## Acceptance criteria

1. External client can create/update each supported content entity synchronously
   with one integration key.
2. Unknown payload shapes are rejected and never stored as arbitrary JSON.
3. Repeated external_id writes do not create duplicates.
4. Explicit Topic deletion affects only the Topic aggregate.
5. No import job, Celery worker or automatic missing-object deletion exists.
6. Media binary data is outside PostgreSQL.
7. Protected media never yields a URL without backend access approval.
8. Signed URLs expire and can be reissued after a new access check.
9. OpenAPI, rate limits, stable errors and safe logs cover integration routes.

## Test scenarios

- Valid/invalid/missing integration key.
- Entity create, read, patch, delete and relation validation.
- external_id idempotency and concurrent upsert.
- Unknown JSON field/type rejection.
- Topic cascade deletion and sibling preservation.
- Media MIME/size validation and upload verification.
- Public/demo/private/paid media URL behavior.
- Entitlement denial and signed URL expiry.
- Integration throttling and secret-safe logs.
- Storage provider failure after database commit.

## Dependencies

- Content entities and access contract from spec 002.
- User/auth permissions from spec 001.
- Subscription policy interface for paid media checks.
- Object-storage adapter; provider remains TBD.
- Self-host reverse proxy and HTTPS configuration.

## Open questions

- Concrete object-storage provider and deployment credentials.
- Final upload completion handshake for that provider.
- Whether integration key rotation later becomes database-managed.
