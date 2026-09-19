# Spec: Content catalog and Topic access

Status: Approved for implementation (delegated review 2026-09-19,
`.omp/decisions/2026-09-19-002-content-catalog-access-quorum.md`)

Owning apps: content, media (MediaFile FK target only), common,
subscriptions policy boundary

Risk: High

Related architecture: docs/architecture/domain-model.md,
docs/architecture/auth-and-access.md, docs/architecture/conventions.md

Related decisions: medcore-docs/decisions/0006-anonymous-demo-content.md,
medcore-docs/decisions/0007-content-access-model.md,
medcore-docs/decisions/0008-mvp-auth-content-and-integration-contract.md

## Goal

Создать backend-каталог MedCore с иерархией Subject → Section → Topic и
опциональной теорией, источниками и учебными дочерними сущностями. Backend
должен выдавать только опубликованный контент, применять Topic-level
demo/free/paid access и не раскрывать закрытые body или media.

## Scope

- Subject, Section и Topic.
- Автоматически генерируемые slugs как вспомогательные URL-представления.
- Topic access_level: demo, free, paid.
- Topic status: draft, published.
- Упорядоченные ContentBlock и ContentBlockType.
- MVP-типы blocks: markdown, image, callout.
- Content workflow statuses: draft, generated, reviewed, published.
- Optional Source, связанный с Topic или ContentBlock.
- Явный child demo preview marker.
- Публичный безопасный каталог и авторизованное чтение full/free/paid content.
- Backend access policy boundary через subscriptions, без прямого чтения
  Subscription в content models.
- Physical deletion Topic с каскадом собственных дочерних content objects.

## Out of scope

- Subscription, Plan, trial, payment provider и entitlement lifecycle.
- Независимая ACL для каждого пользователя или child object.
- Preview draft для обычных пользователей.
- Полная история версий.
- Video, audio, table, interactive и произвольные block types.
- Поиск по телу ContentBlock.
- Frontend catalog UI.

## Actors

| Actor | Разрешённые действия |
|---|---|
| anonymous | читать public catalog, demo Topic и explicit demo preview |
| user | читать demo/free и разрешённый paid content |
| editor | создавать, менять, публиковать content через CMS policy |
| admin | полный content CMS access |
| integration | синхронно писать content через отдельный integration key по spec 004 |

## User scenarios

### User Story 1 — catalog discovery (P1)

Гость видит доступный каталог без утечки закрытого контента.

Acceptance scenarios:

1. Given опубликованные Subject, Section и Topic, when anonymous client requests
   catalog, then it receives safe title, description, order and access metadata.
2. Given draft Topic, when anonymous client requests catalog, then draft Topic
   is absent.
3. Given paid Topic, when anonymous client requests metadata, then it sees
   access level and demo availability but not paid body or private media.

### User Story 2 — Topic reading (P1)

Пользователь читает доступную тему с упорядоченной теорией.

Acceptance scenarios:

1. Given published demo Topic, when anonymous user requests it, then all its
   published blocks are returned.
2. Given authenticated user and free Topic, when user requests it, then all
   published blocks are returned.
3. Given authenticated user without entitlement and paid Topic, when user
   requests it, then body is not returned and response is 403.
4. Given authenticated user with entitlement and paid Topic, when user requests
   it, then published blocks are returned.

### User Story 3 — content authoring (P1)

Editor создаёт тему и постепенно наполняет её блоками.

Acceptance scenarios:

1. Given valid Subject/Section/Topic titles, when editor creates them, then
   required relations and generated slugs are persisted.
2. Given a markdown block, when editor sets position and status, then the block
   appears in deterministic order only after it is published.
3. Given an image block with private media, when an authorized client reads it,
   then the body contains only a safe media reference and never a storage
   secret. Signed URL issuance is delivered by spec 004 (see acceptance
   criterion 9); 002 proves the reference and the absence of storage keys.

### User Story 4 — source attribution (P2)

Редактор добавляет optional source к теме или блоку.

Acceptance scenarios:

1. Given valid source metadata, when editor attaches it to Topic or ContentBlock,
   then the relation is returned in the authorized content response.
2. Given source deletion, when source is removed, then only relations are removed
   and Topic/ContentBlock remain.

## Entities

- Subject: верхний уровень каталога.
- Section: дочерняя группа Subject.
- Topic: основная единица учебного доступа.
- ContentBlockType: configured block type record.
- ContentBlock: ordered theory unit owned by Topic.
- Source: optional reusable attribution record attached to Topic or block.
- Media/File: owned by media app; referenced by image block.

## Business rules

1. Topic belongs to exactly one Section; Section belongs to exactly one Subject.
2. Subject, Section and Topic require title; descriptions are optional.
3. Child content is optional; empty Topic remains a valid CMS entity.
4. Topic access_level is exactly demo, free or paid.
5. Topic is the main access boundary. No child ACL table is introduced.
6. Topic demo gives anonymous access according to ADR 0007.
7. A free or paid Topic may expose only child objects marked
   is_demo_preview to anonymous users. When at least one published
   is_demo_preview block exists, the anonymous content response contains
   exactly those blocks; when none exists, the full body requires
   authentication and the request is rejected with 401.
8. Catalog metadata may be public but must not contain protected body/content.
9. Only Topic and child entities with published visibility are returned by
   user-facing content endpoints.
10. Manual content may be created as published. Generated content may start as
    generated and later be reviewed/published.
11. ContentBlock type records are data entities; the MVP seeds markdown, image
    and callout and does not accept unknown types through the public API.
12. Markdown is the only text format. Raw HTML is rejected at write time; no
    server-side renderer or sanitizer is introduced in 002 and the backend
    never renders Markdown. The rendering boundary owns render-time
    sanitization.
13. ContentBlock order is determined by position within one Topic.
14. Source is optional. Source deletion detaches relations without deleting
    content.
15. Explicit Topic deletion affects only that Topic and owned children; sibling
    Topics, Sections and Subjects are untouched.

## Invariants

- Every Topic has exactly one Section and every Section exactly one Subject.
- Every ContentBlock belongs to exactly one Topic and one known type.
- Position is deterministic within a Topic.
- Published user API never returns draft/generated/reviewed body unless a future
  preview spec explicitly authorizes it.
- Anonymous requests never create learning state.
- access_level values are constrained to demo/free/paid.
- Topic deletion removes only the Topic aggregate: it cannot affect sibling
  Topic/Section/Subject rows. Learning-owned rows that reference Topic/Section
  are removed by their owning spec 003 migrations through a database
  `ON DELETE CASCADE`; `content` never imports or calls `learning`.

## Data model

### Subject

- title: required string.
- description: nullable optional string.
- slug: generated string, canonical URL helper; exact redirect history is
  deferred.
- position: integer with deterministic default.
- created_at, updated_at: UTC timestamps.

### Section

- subject: required foreign key.
- title: required string.
- description: nullable optional string.
- slug: generated string.
- position: integer with deterministic default.
- created_at, updated_at: UTC timestamps.

### Topic

- section: required foreign key.
- title: required string.
- description: nullable optional string.
- slug: generated string.
- position: integer with deterministic default.
- status: draft or published.
- access_level: demo, free or paid.
- created_at, updated_at: UTC timestamps.

### ContentBlockType

- key: unique seeded key.
- title/label: required display name.
- active: boolean.

### ContentBlock

- topic: required foreign key.
- block_type: required foreign key.
- position: required integer.
- status: draft, generated, reviewed or published.
- is_demo_preview: boolean, default false.
- markdown_body: required for markdown and callout blocks.
- media: required for image blocks, owned by media app.
- caption: optional for image blocks.
- reviewed_by: nullable User foreign key.
- published_at: nullable UTC timestamp.
- created_at, updated_at: UTC timestamps.

### Source

- title: required string.
- source_type: required controlled value.
- author, year, url, note: optional.
- M2M relations to Topic and ContentBlock.

### Data model contracts (delegated review 2026-09-19)

- Slug: generated from title in the same transaction; unique per model with a
  deterministic `-N` suffix on collision. 002 serves numeric IDs only; public
  slug routing, manual override and redirect/history remain deferred.
- Position: integer, unique per `(parent, position)`. When omitted the service
  locks the parent row and assigns `max(position) + 1`; ordering is
  `(position, id)`. An explicit duplicate is rejected with 409
  `CONTENT_CONFLICT`.
- ContentBlock status is a set, not a linear state machine: editor/admin may set
  any of draft/generated/reviewed/published. `published_at` is set to server UTC
  time on transition to published and cleared when the block leaves published;
  it is never client-supplied. 409 `INVALID_CONTENT_STATE` is reserved for
  publish-time precondition failures (missing body or missing media).
- Controlled values (`access_level`, `status`, `source_type`) are `TextChoices`
  plus database `CheckConstraint`s.
- MediaFile (owned by `media`) carries only the spec 004 metadata fields
  (`storage_key`, `original_name`, `mime_type`, `size_bytes`, `checksum`,
  `visibility`, timestamps). 002 creates this FK target and nothing else;
  upload-url/access-url/storage adapter stay in spec 004. A MediaFile row is not
  proof that a storage object exists.
- FK deletion matrix: `ContentBlock.topic` CASCADE; `Topic.section` and
  `Section.subject` PROTECT; `ContentBlock.block_type` PROTECT;
  `ContentBlock.media` SET_NULL; `ContentBlock.reviewed_by` SET_NULL; Source M2M
  through tables CASCADE. Topic deletion removes the Topic and owned children in
  one transaction and never touches media storage.

## API

All URLs use /api/v1/, plural resource names and trailing slashes. Numeric IDs
are canonical for backend operations. Slug URL stability is additive and does
not replace IDs.

002 exposes read endpoints only. Content authoring is performed through Django
Admin and the content services; content REST CRUD, the integration key and media
endpoints belong to spec 004 and are not implemented here. Every endpoint
declares its own permission because the global DRF default is `IsAuthenticated`;
public catalog and search endpoints are explicitly anonymous, and list endpoints
use page-number pagination with default page size 20 and maximum 100.

### Public catalog

- GET /api/v1/subjects/
- GET /api/v1/subjects/{id}/
- GET /api/v1/sections/{id}/
- GET /api/v1/topics/
- GET /api/v1/topics/{id}/

Authentication: anonymous allowed.

Response includes safe metadata, status visible to the catalog policy, access
level, ordering and demo availability (`has_demo_preview` is true when at least
one published `is_demo_preview` block exists). Protected body and private
storage keys are excluded.

### Topic content

- GET /api/v1/topics/{id}/content/

Authentication/access: evaluated by Topic access policy.

Response returns ordered published ContentBlock records that the actor may
read. Child demo preview filtering is applied for anonymous access:
`demo` topics return all published blocks; `free`/`paid` topics return exactly
the published `is_demo_preview` blocks when at least one exists, otherwise 401
`AUTHENTICATION_REQUIRED`. Draft/generated/reviewed topics are 404. Authenticated
users without entitlement on a `paid` topic receive 403
`TOPIC_ENTITLEMENT_REQUIRED`. Image blocks expose only a safe media reference;
signed URL issuance is spec 004.

### Sources

Sources may be included in Topic/content responses according to serializer
contract. Source metadata is never required for content access.

### Search

- GET /api/v1/search/?q=&subject_id=&section_id=&page=

Search is case-insensitive title search over Subject, Section and Topic. Body
search and ranking are out of scope.

## Permissions

| Operation | anonymous | user | editor | admin |
|---|---:|---:|---:|---:|
| safe catalog | allow | allow | allow | allow |
| demo Topic | allow | allow | allow | allow |
| free Topic | deny full body | allow | allow | allow |
| paid Topic | deny full body | entitlement only | entitlement policy for user API | entitlement policy for user API |
| CMS write | deny | deny | allow | allow |
| delete Topic | deny | deny | according to CMS policy | allow |

Editor/admin CMS access is separate from user-facing paid entitlement. A CMS
preview must not silently change the user-facing access policy. The CMS write
and delete rows describe the Django Admin/content-service surface and the future
spec 004 REST surface; editor/admin role never bypasses the user-facing paid
policy, and 002 exposes no write endpoints.

## Validation

- titles reject null/empty/whitespace-only values.
- relation IDs must belong to the expected parent.
- access_level/status/type values are controlled values.
- position is an integer, unique per `(parent, position)`; omitted position is
  assigned deterministically by the service and an explicit duplicate is
  rejected with 409 CONTENT_CONFLICT.
- markdown/callout body is non-empty.
- image block requires a valid Media/File reference at write and publish time.
- raw HTML tags and unsafe URL schemes in markdown are rejected at write time
  with 422 VALIDATION_ERROR; no server-side sanitizer is added.
- Source URL, when present, is validated as a URL.
- only editor/admin may set workflow status or published_at; published_at is
  server-assigned.

## Errors

Use the backend envelope with code, detail and optional fields.

| Condition | HTTP | Code |
|---|---:|---|
| missing parent or resource | 404 | RESOURCE_NOT_FOUND |
| inaccessible paid body | 403 | TOPIC_ENTITLEMENT_REQUIRED |
| anonymous free/paid body without any published demo preview | 401 | AUTHENTICATION_REQUIRED |
| draft content in user API | 404 | RESOURCE_NOT_FOUND |
| invalid parent relation | 422 | INVALID_RELATION |
| invalid status transition | 409 | INVALID_CONTENT_STATE |
| duplicate slug/position conflict | 409 | CONTENT_CONFLICT |
| invalid block payload | 422 | VALIDATION_ERROR |
| throttled request | 429 | THROTTLED |

The API must not reveal whether a hidden object exists when the chosen access
policy treats it as unavailable.

## Edge cases

- Empty Topic is valid and can remain draft.
- Published Topic with no published blocks returns an empty ordered list.
- Topic access changes from paid to free without deleting learning state.
- Child demo marker on a draft block has no public effect.
- Deleted Source leaves content valid.
- Deleted media reference prevents image block publication until repaired.
- Duplicate generated slug receives deterministic collision handling; exact
  redirect/history behavior remains outside this spec.
- A child object never overrides Topic access with a broader permission.

## Transactions

- Create/update hierarchy writes are atomic per entity.
- Publish Topic and required status/published_at updates are atomic.
- Topic deletion and owned-child cascade are one transaction.
- Source deletion detaches links in the same transaction and never deletes
  referenced content.
- Storage deletion for media is coordinated after database commit by the media
  spec; a storage failure must not leave a false public URL.

## Concurrency

- Database constraints protect parent ownership, access enum, `(parent,
  position)` uniqueness and per-model slug uniqueness.
- Concurrent Topic/ContentBlock creation under one parent cannot produce
  nondeterministic visible ordering (parent row lock plus deterministic
  assignment).
- Concurrent publication uses service transaction and final database state,
  not stale serializer input.

## Background jobs/events

None for content authoring or read access in this MVP. External content writes
are synchronous under spec 004.

## Security

- Backend, not frontend, enforces Topic access.
- Content serializers never expose storage credentials, raw internal flags or
  unpublished body to user-facing actors.
- Markdown is never rendered by the backend; unsafe markup is rejected at
  write time and the frontend rendering boundary owns render-time sanitization.
- Rate limits apply to public catalog/search and content endpoints.
- Editor/admin audit context is logged without sensitive body or credentials.

## Risks, compatibility and rollout

- Existing apps/content models are skeletons; migrations will create the domain
  model from this spec.
- Central ADR 0004 contains older TBD/optional relations; ADR 0008 and this
  approved spec take precedence for this slice.
- Frontend must not assume the prototype's localStorage/email/demo payloads.
- Paid access calls the subscriptions policy boundary, while its internal model
  is intentionally deferred.

## Acceptance criteria

1. The hierarchy can represent multiple Subjects, Sections and Topics with only
   title as the required user-provided field.
2. User API never returns unpublished or unauthorized body.
3. Topic access matrix matches demo/free/paid rules. The `demo`, `free` and
   `paid`-without-entitlement rows are verified in 002; the `paid`-with-
   entitlement row is proven through the subscriptions policy seam and ships
   enabled by the separate subscriptions feature.
4. Anonymous demo never creates UserTopicProgress, FlashcardReview or
   QuizAttempt. Those models do not exist in 002; the invariant is owned by
   spec 003 and 002 only guarantees it writes no learning state.
5. ContentBlock ordering and the three MVP block types are deterministic.
6. Sources remain optional and can be attached to Topic or ContentBlock.
7. Topic deletion removes only the Topic aggregate and owned children.
8. Catalog, topic content, search and error schemas are in OpenAPI.
9. Private/paid media is represented only by access-checked signed URL behavior
   from spec 004. 002 delivers the FK reference and never exposes storage keys;
   URL issuance itself is verified in spec 004.

## Test scenarios

- Model constraints, parent ownership and enum values.
- Catalog visibility for anonymous, free and paid topics.
- Demo preview filtering inside free/paid Topic.
- Draft/generated/reviewed/published visibility.
- Markdown, image and callout validation, raw-HTML rejection and storage-key
  non-exposure.
- Ordering and duplicate position behavior.
- Source attach/detach/delete behavior.
- Editor/admin permissions and user-facing paywall (deny path plus policy-seam
  allow path).
- Topic cascade deletion and sibling preservation.
- Search filters, pagination and no body leakage.
- Concurrent parent/slug/order writes.

## Dependencies

- users auth from spec 001.
- media model and signed URL contract from spec 004; 002 creates only the
  MediaFile FK target (metadata fields) and defers upload/access-url/storage.
- subscriptions access policy boundary; payment semantics are deferred. 002
  ships the policy interface and the deny-by-default result.
- PostgreSQL migrations and DRF/OpenAPI.

## Open questions

- Exact slug uniqueness scope and redirect/history policy are not needed for
  numeric-ID CRUD and must be settled before public slug URLs are implemented.
- Final media provider is intentionally TBD.
