# Research: Content catalog and Topic access

**Feature**: `002-content-catalog-access`  
**Date**: 2026-09-19  
**Decision record**: [delegated review](../../.omp/decisions/2026-09-19-002-content-catalog-access-quorum.md)

## Sources consulted

- `specs/002-content-catalog-access/spec.md` and its requirements checklist.
- `specs/004-content-api-media/spec.md` — MediaFile field set, upload/access-url
  ownership, pagination 20/100, media deletion repair workflow.
- `specs/003-learning-state/spec.md` — learning cleanup follows an approved
  content deletion contract; User FK cascade from the 001 decision.
- `../medcore-docs/decisions/0002-flexible-content-blocks.md`,
  `0004-mvp-decision-register.md`, `0006-anonymous-demo-content.md`,
  `0007-content-access-model.md`, `0008-mvp-auth-content-and-integration-contract.md`.
- `docs/architecture/target-architecture.md`, `domain-model.md`,
  `auth-and-access.md`, `conventions.md`, `open-questions.md`.
- Existing `apps/users` implementation and `.omp/decisions/2026-09-18-001-*.md`.

## Findings

### Media is a hard dependency of this slice

ADR 0008 fixes `markdown`, `image` and `callout` as the MVP theory blocks, and
spec 002 requires an image block to carry a `Media/File` reference. Spec 004 owns
`MediaFile` and the upload/access-url endpoints but declares a dependency on the
002 content entities, so it cannot ship first. The least-risk resolution is to
create the metadata-only `MediaFile` model in `apps.media` exactly as spec 004
lists it, keep the FK in content, and leave the provider, upload handshake and
signed URLs to 004.

### Entitlement has no storage yet

`apps.subscriptions` is an empty skeleton; no `Plan`/`Subscription` model exists
and the entitlement lifecycle is explicitly out of scope for 002. ADR 0007
requires paid access only for an active entitlement and a single policy
interface. The honest 002 implementation is a public policy function that
reports no entitlement, with the content access service composing it; the allow
branch is provable by overriding the policy at the boundary. This keeps the
contract real instead of inventing subscription semantics.

### Access model and demo preview

ADR 0007 puts the access boundary on the Topic with `demo/free/paid` and allows
explicit child demo-preview markers inside `free`/`paid` topics. Spec 002 needs
both the preview allowance and the `AUTHENTICATION_REQUIRED` error row, so the
anonymous content response returns the published demo-preview subset when one
exists and otherwise requires authentication for the full body.

### Slug and ordering

`docs/architecture/target-architecture.md` requires slug uniqueness scope and
redirect policy to be defined before public slug URLs exist; 002 serves numeric
IDs only, so slug stays a generated auxiliary field. ADR 0004 item 26 leaves the
ordering mechanism open while spec 002 requires deterministic ordering and a
`CONTENT_CONFLICT` error for duplicate positions; a `(parent, position)` unique
constraint with locked deterministic assignment satisfies both.

### Raw HTML

ADR 0004 item 25 left the raw-HTML policy open, and
`docs/architecture/conventions.md` assigns it to the content spec while
forbidding unnecessary dependencies. The project has no markdown or sanitizer
library, so 002 rejects HTML tags and unsafe URL schemes at write time instead of
adding a sanitizer; the backend does not render Markdown.

### Deletion

ADR 0004 item 34 makes Topic deletion cascade to its owned children, and
`docs/architecture/domain-model.md` extends cascading to dependent learning data
for the relevant spec. The accepted 001 pattern is that the owning app declares
the cross-domain DB cascade contract without importing the other domain. 002
therefore keeps Section/Subject/block-type rows protected, cascades only owned
children, and declares that spec 003 ships the learning-owned cascades.

### Search

ADR 0004 items 81-85 fix `icontains` search over `Subject.title`,
`Section.title` and `Topic.title` with subject/section filters, standard DRF
pagination and no ranking or body search. No search engine or index is added.

## Decisions carried into the plan

1. Create the media FK target only; defer URLs/storage to 004.
2. Deny-by-default subscriptions policy seam; prove the allow path in tests.
3. Read API plus Django Admin/services authoring; REST CRUD in 004.
4. Anonymous free/paid returns the published demo-preview subset, else 401.
5. Global per-model slug uniqueness with a deterministic suffix; `(parent,
   position)` uniqueness with locked assignment and 409 on duplicates.
6. Reject raw HTML and unsafe URL schemes; no sanitizer dependency.
7. FK matrix: topic CASCADE; section/subject/block-type PROTECT; media/reviewer
   SET_NULL; Source M2M CASCADE.
8. Status is a set of four workflow values; `published_at` is server-assigned;
   409 `INVALID_CONTENT_STATE` only for publish preconditions.
9. Explicit `AllowAny` on public reads, page-number pagination 20/100, scoped
   throttle rates, 422 rows raised as explicit `APIError`.
10. `ContentBlockType` values are seeded by an idempotent data migration.

## Open items intentionally not closed

- Final media provider, upload handshake and MIME allow-list (spec 004).
- Public slug URLs, manual override and redirect/history.
- Subscription/Plan/trial/payment semantics (separate feature).
- Flashcard/Quiz demo-preview markers and learning state (specs 003/004).