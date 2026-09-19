# Implementation Plan: Synchronous content API and protected media

**Branch**: `feature/004-content-api-media`
**Date**: 2026-09-19
**Spec**: [spec.md](./spec.md)
**Decision record**: [delegated review](../../.omp/decisions/2026-09-19-004-content-api-media-review.md)

## Summary

Deliver the synchronous authoring and media surface of MedCore. `apps.content`
gains Flashcard/Quiz/QuizQuestion/QuizAnswer, an optional `external_id` identity
on the seven top-level entities, the write services and the strict REST CRUD
surface under `/api/v1/content/`, authenticated either by the configured
integration key or by an editor/admin JWT. `apps.media` gains the metadata CRUD,
the provider-neutral storage adapter (local dev/test backend and S3-compatible
backend), the upload contract and the access-checked signed read URL.
`apps.common` gains the integration credential primitive; `apps.content`
provides the two content-owned policies the media app needs (access decision and
deletion guard) through fail-closed settings entries, so `media` never imports
`content`. Entitlement still resolves only through `apps.subscriptions.policy`.

## Technical Context

**Language/Version**: Python 3.12
**Framework**: Django + Django REST Framework
**Storage**: PostgreSQL; object storage behind the adapter boundary (local
filesystem for dev/test, S3-compatible for deployment); Redis only for shared
DRF throttle counters
**Testing**: pytest, pytest-django, DRF APIClient, live PostgreSQL
**API**: REST/JSON under `/api/v1/`, drf-spectacular OpenAPI
**Pagination**: DRF page-number, default 20, maximum 100
**Throttles**: `integration_write` 120/min, `media_upload` 30/min,
`media_access` 60/min
**New dependency**: `boto3` as an optional dependency group (`storage-s3`) and a
dev-group entry so the adapter is covered by tests; no new infrastructure
**Constraints**: no signals, no Celery/queue, no repository layer, no
subscription-field reads, no `storage_key` exposure, no child deletion, no
production dependency on the local filesystem backend

## Constitution Check

| Gate | Result | Evidence |
|---|---|---|
| Source-of-truth precedence | PASS | Decision record resolves every gap from ADRs 0004/0006/0007/0008 and `docs/architecture`; no accepted decision is overridden (002's `SET_NULL` is preserved). |
| Domain ownership | PASS | `content` owns authoring entities and the access decision; `media` owns metadata, adapter and URL issuance; `common` owns the transport credential primitive; `subscriptions` owns entitlement. |
| Dependency direction | PASS | `content → media` and `content → users`; `media` imports no business domain (the two content policies arrive through settings); no reverse import. |
| Contract-first API | PASS | `contracts/content-api.md` and `contracts/media-api.md` fix every route, payload, status and error before coding. |
| Security boundary | PASS | Constant-time key comparison, marked-route scope, authorization before storage access, allow-listed MIME/size, capability tokens without the storage key, no secret logging. |
| Data/migration safety | PASS | Forward-only migrations; `external_id` and the new models are additive; `ContentBlock.media` keeps `SET_NULL`; uniqueness and check constraints as the race backstop. |
| MVP simplicity | PASS | Django ORM, Django Admin, one integration key, synchronous services, one adapter interface with two implementations. |
| Test evidence | PASS | Tests cover the integration key matrix, strict payloads, `external_id` upsert, aggregate quiz writes, cascade deletion, media upload verification, the access matrix, signed URL expiry, the delete guard under concurrency, throttling and OpenAPI. |

## Design decisions

1. **Integration credential** — `apps/common/integration.py` owns the header
   authentication class, the non-User principal, `HasIntegrationKey`,
   `IsContentAuthor` (active user with `role in {editor, admin}` or superuser)
   and `IsNotIntegrationClient`. The authenticator runs first on marked routes
   and hard-fails a present-but-wrong key. `MEDCORE_CONTENT_API_KEY` unset denies
   everything. `apps/content/admin.py` reuses the shared role constant.
2. **Content CRUD** — thin `GenericAPIView`-based views (no router, matching the
   app's existing style), strict write serializers that reject unknown fields,
   services for every mutation, selectors for list reads, explicit
   `extend_schema` metadata.
3. **Quiz aggregate** — one service, one transaction, nested upsert by optional
   `id`, no child deletion, ≥1 question / ≥2 answers / ≥1 correct answer,
   deterministic positions, `(parent, position)` uniqueness.
4. **`external_id`** — nullable unique column on the seven top-level entities;
   `POST` upserts on a known identity (200) or creates (201); established
   identity is immutable (409); lookup and mutation inside the write
   transaction.
5. **Media storage** — `StorageAdapter` protocol with `LocalStorageAdapter`
   (capability URLs to the controlled upload/download endpoints) and
   `S3StorageAdapter` (presigned URLs). `MEDIA_STORAGE_BACKEND` selects; a
   system check refuses the local backend outside `DEBUG`.
6. **Media access** — `access-url` is `AllowAny`; public media is signed for
   everyone; protected media uses the content-owned access decision, which
   reuses `apps.content.access.evaluate_topic_access` and the 002 demo-preview
   rule; authorization precedes `verify_object`, which precedes signing.
7. **Media deletion** — `apps.media.services.delete_media_file` locks the media
   row, calls the content-owned guard, deletes and schedules storage cleanup in
   `transaction.on_commit`. `publish_content_block` locks the referenced media
   rows before the block row and rejects a changed reference with 409
   `CONTENT_CONFLICT`, so publish and delete serialize.
8. **Policy seam** — `MEDIA_ACCESS_POLICY_PROVIDER` and
   `MEDIA_DELETE_GUARD_PROVIDER` are resolved with `import_string` and fail
   closed. This keeps `/api/v1/media/` route ownership in `apps.media` while the
   access and integrity rules stay in `apps.content`.
9. **Errors** — reuse the `{code, detail, fields}` envelope; raise `APIError`
   explicitly for 401/403/404/409/422 so the stable codes match the contracts.

## Project structure

```text
apps/common/
├── integration.py        # header auth, principals, author/scope permissions
└── permissions.py        # CONTENT_AUTHOR_ROLES + IsContentAuthor (shared)

apps/content/
├── models.py             # + Flashcard, Quiz, QuizQuestion, QuizAnswer, external_id
├── services.py           # + flashcard/quiz/source/upsert services, media-locked publish
├── selectors.py          # + CRUD read selectors
├── serializers.py        # + strict write serializers, nested quiz, read serializers
├── views.py              # + content CRUD views
├── urls.py               # + /content/ routes
├── media_policy.py       # decide_media_access, guard_media_deletion
├── admin.py              # + new models, shared role constant
└── migrations/0003_*.py

apps/media/
├── storage.py            # StorageAdapter, Local, S3, resolver
├── services.py           # metadata CRUD, upload/access issuance, guards
├── serializers.py        # strict media write serializer, metadata/signed-url serializers
├── views.py              # media CRUD + upload/access + controlled endpoints
├── urls.py               # /media/ routes
├── checks.py             # local backend refused outside DEBUG
├── admin.py              # staff + role gate
└── tests/

config/settings/base.py   # integration key, media settings, throttle scopes
config/urls.py            # include media routes
.env.example              # new settings documented
```

## Implementation order

1. Settings, integration credential primitive, content models with `external_id`
   and the four quiz models plus the migration.
2. Content write services (flashcard, quiz aggregate, source relations,
   `external_id` upsert, media-locked publish) and selectors.
3. Content serializers, CRUD views, URL wiring, OpenAPI metadata.
4. Media storage adapter, services, serializers, views, URLs, system check,
   admin gate, `media_policy` on the content side.
5. Story tests for both apps, then the quickstart smoke and the full AGENTS
   checks.

## Risks and mitigations

- **Provider still unselected**: the local backend is dev/test only and refused
  in production by a system check; the S3-compatible adapter is the deployment
  extension point. Recorded as residual risk.
- **Policy seam misconfiguration**: fail-closed defaults deny protected media and
  refuse deletion; covered by tests.
- **Lock order**: media row first, then content rows, in both the delete and
  publish paths; covered by a concurrency test.
- **Quiz children are append/update only**: deliberate narrowing recorded in the
  decision record; spec 003 owns attempt-time deletion policy.
- **Strict field rejection** may break a client sending extra fields; that is the
  documented contract (business rule 3).
- **`paid` media** stays unreachable until the subscriptions feature ships the
  entitlement source.

## Complexity Tracking

No constitution violations. No Repository/UnitOfWork/EventBus layer, queue,
provider infrastructure, search engine or unrelated refactor is introduced. The
only new dependency is the optional S3 SDK used by the adapter it implements.
