# Implementation Plan: Content catalog and Topic access

**Branch**: `feature/002-content-catalog-access`  
**Date**: 2026-09-19  
**Spec**: [spec.md](./spec.md)  
**Decision record**: [delegated review](../../.omp/decisions/2026-09-19-002-content-catalog-access-quorum.md)

## Summary

Build the MedCore content catalog in `apps.content`: the
`Subject → Section → Topic` hierarchy, ordered `ContentBlock`s with a
`ContentBlockType` registry (`markdown`, `image`, `callout`), optional `Source`
attribution and the `MediaFile` FK target owned by `apps.media`. The feature
serves a public, safe catalog; an access-controlled Topic content endpoint that
applies the ADR 0007 `demo/free/paid` matrix with an explicit child
demo-preview allowance; and a case-insensitive title search. Write use cases
(slug/position assignment, publish, delete) live in services and are exposed
through Django Admin; content REST CRUD, media upload and signed URLs stay in
spec 004. Paid entitlement is resolved only through the public
`apps.subscriptions.policy` interface.

## Technical Context

**Language/Version**: Python 3.12  
**Framework**: Django + Django REST Framework  
**Storage**: PostgreSQL; Redis only for shared DRF throttle counters  
**Testing**: pytest, pytest-django, DRF APIClient, live PostgreSQL  
**API**: REST/JSON under `/api/v1/`, drf-spectacular OpenAPI  
**Pagination**: DRF page-number, default 20, maximum 100  
**Throttles**: scoped rates for `catalog`, `content_read`, `search`  
**Deletion**: Topic aggregate CASCADE; Section/Subject/block-type PROTECT;
media/reviewer SET_NULL; Source M2M CASCADE  
**Constraints**: no signals, no repository/queue layer, no Subscription read in
content, no storage key exposure, no sanitizer/markdown dependency,
forward-only migrations  
**Scope**: catalog + read access + Admin authoring + search; subscriptions,
media upload/URLs, learning state, flashcards, quizzes and frontend are out of
scope

## Constitution Check

| Gate | Result | Evidence |
|---|---|---|
| Source-of-truth precedence | PASS | Decision record resolves every gap from ADRs 0004/0006/0007/0008 and `docs/architecture`; no accepted decision is overridden. |
| Domain ownership | PASS | `content` owns authoring entities and Admin; `media` owns `MediaFile`; `subscriptions` owns entitlement policy; no reverse imports. |
| Dependency direction | PASS | `content → media` (metadata reference) and `content.application → subscriptions.policy` only, per `target-architecture.md`. |
| Contract-first API | PASS | `spec.md` and `contracts/content-api.md` fix every endpoint, permission, status and error before coding. |
| Security boundary | PASS | Backend enforces access; serializers expose no storage key or unpublished body; raw HTML rejected; throttles documented. |
| Data/migration safety | PASS | Forward migrations, DB `CheckConstraint`s and uniqueness; `media.0001` precedes `content.0001`. |
| MVP simplicity | PASS | One domain app, Django ORM, Django Admin, no new dependency or infrastructure. |
| Test evidence | PASS | Tests cover catalog visibility, access matrix, demo preview, workflow, ordering/slug, cascade, search, permissions and OpenAPI. |

## Design decisions

1. **Owning apps**: models/services/selectors/serializers/views/URLs/Admin in
   `apps.content`; the `MediaFile` FK target in `apps.media`; the entitlement
   boundary in `apps.subscriptions.policy`; a standard pagination primitive in
   `apps.common.pagination`.
2. **Media boundary**: create only the spec 004 `MediaFile` metadata model.
   `ContentBlock.media` is `SET_NULL`; publish re-checks that an image block has
   media. No adapter, upload-url or access-url in 002.
3. **Entitlement boundary**: `has_paid_content_entitlement(user)` returns the
   honest deny-by-default result; content's access service composes it and
   raises `TOPIC_ENTITLEMENT_REQUIRED`. Tests override the policy to prove the
   allow branch.
4. **Catalog reads**: `selectors` provide published-only catalog queries with
   `prefetch_related`; `has_demo_preview` is annotated from published demo
   blocks; no body or storage key is serialized.
5. **Access composition**: `apps.content.access.evaluate_topic_access` combines
   the topic's `access_level`, the actor's authentication state and the
   subscriptions policy into a ready access decision used by the content
   selector and view.
6. **Authoring**: `services` own slug generation (deterministic suffix), locked
   position assignment, publish validation and `published_at`, and Topic
   deletion. Django Admin calls the services and gates on
   `is_staff` + `role in {editor, admin}`.
7. **Validation**: raw HTML tags and unsafe URL schemes are rejected in
   `markdown_body`; per-type required fields are enforced in the serializer/
   service and re-checked at publish time; controlled values get
   `TextChoices` + DB `CheckConstraint`s.
8. **Errors**: reuse the `{code, detail, fields}` envelope; raise `APIError`
   explicitly for 401/403/404/409/422 so the stable codes match the spec.

## Research summary

- ADR 0007/0008 fix the Topic access boundary, `demo/free/paid`, child demo
  preview and the three MVP block types, so image blocks cannot be dropped.
- Spec 004 declares the `MediaFile` field set and owns upload/URLs; it depends
  on spec 002 content entities, so the FK target must ship in 002.
- `docs/architecture/target-architecture.md` permits `content → media`
  references and only a public `subscriptions.policy` call from the content
  application layer.
- The 001 decision record establishes the cross-domain deletion pattern (owner
  declares the DB cascade contract); 002 mirrors it for learning-owned FKs.
- PostgreSQL `icontains` search is the accepted MVP search; no ranking,
  full-text index or Elasticsearch is added.

## Project structure

```text
apps/content/
├── models.py          # Subject, Section, Topic, ContentBlockType, ContentBlock, Source
├── services.py        # slug/position assignment, save/publish/delete use cases
├── selectors.py       # published catalog, topic content, search queries
├── access.py          # demo/free/paid + demo-preview decision composition
├── validators.py      # raw-HTML / unsafe-URL rejection for markdown_body
├── serializers.py     # read serializers (no secrets, no unpublished body)
├── views.py           # thin read endpoints with OpenAPI metadata
├── urls.py            # /api/v1/ catalog, content, search routes
├── admin.py           # Django Admin with content permission hook
├── apps.py
├── migrations/0001_initial.py
└── tests/
    ├── conftest.py
    ├── test_models.py
    ├── test_services.py
    ├── test_selectors.py
    ├── test_access.py
    └── test_api.py

apps/media/
├── models.py          # MediaFile metadata (FK target only)
└── migrations/0001_initial.py

apps/subscriptions/
├── policy.py          # has_paid_content_entitlement(user)
└── tests/test_policy.py

apps/common/
└── pagination.py      # standard page-number pagination (20/100)

config/
├── settings/base.py   # throttle scopes, pagination, no sanitizer dependency
└── urls.py            # include content routes

specs/002-content-catalog-access/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/content-api.md
└── tasks.md
```

## Implementation order

1. Add `apps/media` MediaFile model and migration; add the subscriptions policy
   module and the common pagination primitive.
2. Add content models, constraints and the initial migration (depends on media).
3. Implement validators, services (slug/position/publish/delete) and selectors.
4. Implement the access composition and read serializers.
5. Implement the read endpoints, URL wiring, throttles and OpenAPI metadata.
6. Register Django Admin with the content permission hook and service-backed
   saves; seed `ContentBlockType` values with an idempotent data migration.
7. Write story tests, then run the quickstart smoke and the full AGENTS checks.

## Risks and mitigations

- **Paid content unreachable until subscriptions ships**: documented; the deny
  path is real and the allow path is proven through the policy seam.
- **Media model churn**: bound to the spec 004 field set; 004 changes need a
  forward migration.
- **Slug/position narrowing**: recorded; later scope changes need a data
  migration, never a rewrite of applied history.
- **Admin bypassing services**: Admin saves route through services, and
  `(parent, position)` uniqueness plus validation keep it consistent.
- **Search scalability**: MVP `icontains` over titles with a merged, paginated
  result list; ranking and body search stay out of scope.
- **Learning cascade contract**: 002 declares the contract; spec 003 ships the
  learning-owned `ON DELETE CASCADE` migrations.

## Complexity Tracking

No constitution violations. No Repository/UnitOfWork/EventBus layer, queue,
provider, search engine or unrelated refactor is introduced.