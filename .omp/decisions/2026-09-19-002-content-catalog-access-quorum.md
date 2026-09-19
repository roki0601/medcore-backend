# Delegated review decision: content catalog and Topic access

- Feature: `002-content-catalog-access`
- Workflow state: `SPEC_REVIEW` → `DELIBERATING` → `READY_FOR_PLAN`
- Decision status: accepted for this feature implementation
- Decision time: 2026-09-19T06:10:28Z
- Review roles and model identifiers:
  - DeepSeek `spec-reviewer`: `openrouter/deepseek/deepseek-v4.1-flash:high`
  - Luna `watchdog`: `openai-codex/gpt-5.6-luna:high`
  - DeepSeek `architect`: `openrouter/deepseek/deepseek-v4.1-flash:max`

## Question and affected workflow state

Feature 002 was a Draft, High-risk spec. `SPEC_REVIEW` could not advance until the
delegated review resolved: the media dependency on an unapproved sibling spec
ordered later (004), the entitlement boundary with no Subscription model, the
unspecified CMS write boundary, an internal anonymous-access contradiction, the
slug/position uniqueness scope, the raw-HTML policy, the FK cascade matrix, the
Topic-deletion-vs-learning contract, and the per-endpoint permission/pagination
contract. A stale `PROJECT_STATE.md` also still asked for human review of PR 2.

## Preflight evidence

Three-repository preflight on `main`, all fast-forward, all worktrees clean:

- `medcore-docs` `0b1d51c` (`origin/main`)
- `medcore-backend` `e530c4f` (`origin/main`) — feature branch created from it
- `medcore-frontend` `db3473d` (`origin/main`)

`gh pr list` shows PR #1/#2/#3 in `medcore-backend` (and the docs/frontend
preflight PRs) `MERGED`; `main` contains the merge commits. The
`PROJECT_STATE.md` "human review required before 002" line is stale, so it is not
a live gate; `PROJECT_STATE.md` is refreshed by this run.

## Authoritative evidence

- `AGENTS.md:36-52,52-61,71-85,107-127` — preflight; content owns the catalog;
  no paywall checks in content models; unresolved decisions require a
  source-backed delegated record; migrations forward-only.
- `.omp/AUTONOMOUS_REVIEW.md:11-14,47-83,85-102` — manager performs the
  source-backed review and resolves blockers; at most two bounded rounds; every
  resolution gets a decision record.
- `specs/002-content-catalog-access/spec.md` — entities, business rules,
  invariants, access matrix, API, validation, errors, transactions, acceptance
  criteria and test scenarios (whole file).
- `.omp/decisions/2026-09-18-001-telegram-auth-account-quorum.md:145-154` —
  accepted cross-domain deletion pattern: the owning app declares the DB
  `ON DELETE CASCADE` contract and never imports the other domain.
- `../medcore-docs/decisions/0006-anonymous-demo-content.md` and
  `0007-content-access-model.md:19-30,41-64` — anonymous demo scope; Topic-level
  `demo/free/paid`; child demo-preview marker; one subscriptions policy
  interface; content/learning never read Subscription fields.
- `../medcore-docs/decisions/0008-mvp-auth-content-and-integration-contract.md:46-56,85-109`
  — title-only user input, generated auxiliary slug, markdown/image/callout MVP
  blocks, Topic as access boundary, one-origin hosting, provider/slug scope
  explicitly deferred.
- `../medcore-docs/decisions/0004-mvp-decision-register.md:32-51,131-138,147-152,189-200`
  — TBD items that spec 002 closes or defers (slug scope, ordering, raw HTML,
  Topic cascade, Django Admin CMS, editor/admin mapping); image media is a
  separate Media/File model.
- `docs/architecture/target-architecture.md:67-76,96-120,145-181,198-231` — app
  ownership, allowed dependency direction (`content → media`,
  `content.application → subscriptions.policy`), thin views, services/selectors,
  transaction boundaries, no subscription-field reads in content.
- `docs/architecture/domain-model.md:57-58,100-102,131-133,159-188` — content
  ownership, status set is not a mandatory linear state machine, Topic deletion
  cascades to dependent content and learning data per the relevant spec.
- `docs/architecture/conventions.md:34-74,76-109,132-156` — error envelope, HTTP
  status table, validation layers, transaction/constraint requirements.
- `docs/architecture/auth-and-access.md:51-52,62-64,131-136` — child demo
  preview if the content spec defines it; editor/admin role does not imply
  premium on the user API; each feature spec must declare per-endpoint
  permissions.
- `specs/003-learning-state/spec.md:289-290,311-312` — learning cleanup follows
  Topic deletion only through an explicitly approved content deletion contract.
- `specs/004-content-api-media/spec.md:156-167,210-222,229-232,264-286,369-375` —
  MediaFile field set and ownership, upload/access-url endpoints, page-number
  pagination 20/100, media deletion repair workflow, provider TBD.
- Existing code facts: `apps/{content,media,subscriptions,learning}/models.py`
  are empty skeletons; `config/settings/base.py:63-69,173-180` has no content
  throttle scopes, no pagination class and a global `IsAuthenticated` default;
  `apps/common/exceptions.py:76-84` maps serializer validation to
  `INVALID_REQUEST/400` and plain 403 to `PERMISSION_DENIED`; `apps/users` has
  no editor/admin permission surface.

## Independent findings

### DeepSeek spec-reviewer

`NEEDS_HUMAN_REVIEW`: the spec is not implementation-ready as written — one
internal contradiction (anonymous free/paid body vs the 401 row), AC9/US3.3
signed media URL unreachable in this slice, and five unstated contracts
(entitlement surface, CMS write boundary, status transitions, slug/position
uniqueness, raw-HTML policy). It also flagged that the written policy text does
not explicitly name a quorum-based spec-approval authority.

### Luna watchdog

`BLOCKED` on two workflow items — the (stale) PROJECT_STATE 001 gate and the
Draft/TBD status — and `RESOLVED` on the technical questions: minimal media
model in 002 with URL/upload deferred to 004; deny-by-default
`subscriptions.policy` with the allow path proven through the policy seam;
Django Admin/service authoring with REST CRUD in 004; anonymous free/paid returns
the published demo-preview subset, otherwise 401; numeric-ID CRUD defers public
slug scope; reject raw HTML at validation; media FK must be protected/restricted
at the DB level and Topic deletion must not delete media storage.

### DeepSeek architect

`READY` conditional on recording these resolutions and amending the spec text.
Full matrix: media model scope, policy seam, CMS/admin mapping, anonymous
preview semantics, slug scope, position ordering, FK cascade matrix, learning
cascade contract, status transitions, per-type required fields, per-endpoint
permission/pagination. It judged every gap resolvable from a higher-priority
source with no irreconcilable conflict.

## Deliberation and rebuttal

Round 1 — all three reviewers independently agreed 002 must ship image blocks
(ADR 0008) and therefore needs a media FK target; none accepted dropping image
blocks. The watchdog and architect converged on creating the minimal
`media.MediaFile` model in 002 while spec 004 keeps upload/access-url/storage.

Round 2 — the anonymous-access contradiction was resolved by the majority
(watchdog, architect): keep ADR 0007's preview allowance and give the 401 error
row a real trigger (no published preview block exists). The spec-reviewer's
alternative (always 200, possibly empty, delete the 401 row) was rejected
because it deletes an explicit accepted error contract that the reviewer could
not replace with a source.

Round 3 — slug/position: the reviewer preferred parent-scoped slug uniqueness
and a `(parent, position)` unique constraint; the architect preferred global
slug uniqueness and a `(position, id)` tiebreak without a position constraint.
The manager adopted the combination that preserves the spec's own error table:
global-unique slug with deterministic `-N` suffix, and a `(parent, position)`
unique constraint with locked deterministic auto-assignment; duplicate explicit
positions are rejected as `CONTENT_CONFLICT` (the spec's error row). The
architect's objection is recorded as residual risk for future reorder semantics.

Round 4 — no reviewer dissent remained on the media FK delete direction: the
spec's own edge case ("Deleted media reference prevents image block publication
until repaired") requires the reference to survive media deletion, so
`ContentBlock.media` is `SET_NULL` with a publish-time re-check rather than
`RESTRICT`; the alternative is recorded as rejected.

The spec-reviewer's governance objection (no written quorum authority) is
resolved by the policy itself: `AGENTS.md:9-11,27-32` delegates spec approval and
blocker resolution to the source-backed delegated review recorded in
`.omp/decisions/`, and `.omp/AUTONOMOUS_REVIEW.md` defines that mechanism as an
evidence-backed manager decision with a bounded escalation. This record is that
approval; no separate human gate is required for this High-risk feature.

## Final decision

### 1. Media boundary (002 creates the FK target only)

- Create `apps/media/models.py::MediaFile` with exactly the spec 004 field set:
  `storage_key`, `original_name`, `mime_type`, `size_bytes`, `checksum`,
  `visibility` (`public`/`protected`), `created_at`, `updated_at`. One forward
  migration; no object-storage adapter, no upload-url/access-url endpoints, no
  provider assumption, no signed URLs.
- `ContentBlock.media = FK(MediaFile, null=True, blank=True, on_delete=SET_NULL)`.
  Spec 002's edge case ("deleted media reference prevents image block
  publication until repaired") requires the reference to survive media deletion;
  publish-time re-validation rejects an image block without media. Rejected
  alternative: `RESTRICT` — it would block media deletion and contradicts the
  documented repair path.
- 002 read responses expose only media `id`, `mime_type`, `original_name`,
  `visibility`; `storage_key` and any credential are never serialized.
- Spec 002 US3.3 is amended: URL issuance is delivered by spec 004. AC9 stays
  the controlling statement. 002 must not treat a MediaFile row as proof the
  object exists in storage.
- Migration order: `media.0001` before `content.0001`;
  `content` migration declares the `media` dependency.

### 2. Entitlement boundary (policy seam, deny-by-default)

- Add `apps/subscriptions/policy.py` with one public callable
  `has_paid_content_entitlement(user) -> bool`, implementing the ADR 0007 rule
  "active entitlement". No `Subscription`/`Plan` model is created in 002.
- The 002 implementation returns `False` for every user because no entitlement
  storage exists yet — this is the honest contract behavior, not a fake
  fallback: `paid` genuinely has no entitled users until the subscriptions
  feature ships. Only the content application/access-composition layer calls
  this function; content models, serializers and selectors never import it.
- The allow branch is proven by overriding the policy function in tests. US2.4
  and the "entitled allow" row of AC3 are marked deferred to the subscriptions
  feature.
- Editor/admin role never bypasses user-facing paid access on the user API;
  CMS/Admin access is a separate surface.

### 3. CMS write boundary

- 002 ships content read APIs plus Django Admin and content write services
  (create/save, publish, delete). It exposes no content REST write endpoints;
  REST CRUD and the integration key stay in spec 004.
- Editor/admin access to the content Admin is gated by a content-owned
  permission hook requiring `is_staff` and `User.role in {editor, admin}`;
  superusers retain full access. `content` does not own or mutate roles.
- User Story 3 authoring acceptance is verified through Admin/service tests.

### 4. Anonymous free/paid Topic content

- `demo` Topic, anonymous → 200, all published blocks.
- `free`/`paid` Topic, anonymous → 200 with exactly the published
  `is_demo_preview` blocks when at least one exists; otherwise 401
  `AUTHENTICATION_REQUIRED` (the full body cannot be served without a
  principal). This gives the spec's 401 row a real, testable trigger while
  preserving ADR 0007's preview allowance.
- Authenticated without entitlement on `paid` → 403
  `TOPIC_ENTITLEMENT_REQUIRED`. Draft/unpublished → 404 `RESOURCE_NOT_FOUND`.
  A child demo marker never widens access.

### 5. Slug and position contracts

- Slugs are generated from the title in the same transaction and are
  auxiliary: 002 serves numeric IDs only. Collisions get a deterministic
  `-2`, `-3`, … suffix with a DB unique constraint on the slug column
  (global scope per model). This is the smallest scope, needs no composite
  constraint and can be loosened later by dropping the constraint.
- Position is an integer with deterministic default. Omitted position =
  `max(position) + 1` inside the same transaction with the parent row locked;
  ordering is `(position, id)`. A `(parent, position)` unique constraint plus
  `409 CONTENT_CONFLICT` rejects explicit duplicate positions, matching the
  spec error table. Admin ordering must go through the same service so it can
  never surface an `IntegrityError`.
- Public slug routing, manual override and redirect/history stay deferred to
  the spec that introduces slug URLs.

### 6. Raw HTML policy

- No sanitizer or markdown library dependency is added. `markdown_body` carries
  a validator that rejects HTML tags and unsafe link/image URL schemes
  (`javascript:`, `data:`, `vbscript:`) outside fenced code blocks, with 422
  `VALIDATION_ERROR`; the backend never renders Markdown. The validation must
  tolerate a literal `<` in prose (for example `<5 мм`).
- "Unsafe media content" can only be partially enforced in 002 because the MIME
  allow-list belongs to spec 004; 002 requires a valid MediaFile reference.

### 7. FK cascade and deletion matrix

- `ContentBlock.topic → Topic`: `CASCADE` (the Topic aggregate).
- `Topic.section → Section`, `Section.subject → Subject`: `PROTECT`; 002 defines
  only Topic deletion, so no implicit mass deletion.
- `ContentBlock.block_type → ContentBlockType`: `PROTECT`; retirement uses
  `active`.
- `ContentBlock.media → MediaFile`: `SET_NULL` (see §1).
- `ContentBlock.reviewed_by → users.User`: `SET_NULL` (001 hard-deletes User;
  content must survive).
- `Source` M2M through tables: `CASCADE` (links only, never content).
- Topic deletion removes only the Topic and its owned children in one
  transaction; sibling Topics, Sections and Subjects are untouched. The
  invariant is scoped to the authoring hierarchy: learning-owned FKs to
  Topic/Section ship in spec 003 with database `ON DELETE CASCADE`, mirroring
  the accepted 001 User→learning contract. `content` never imports or calls
  `learning`.

### 8. Status transitions

- ContentBlock status is a set, not a linear state machine: editor/admin may set
  `draft`, `generated`, `reviewed` or `published` directly; manual content may
  be created `published`. `published_at` is set to the server UTC time when a
  block becomes `published` and cleared when it leaves `published`; it is never
  client-supplied.
- `409 INVALID_CONTENT_STATE` is returned only for publish-time precondition
  failures (missing markdown body or missing media reference for the block
  type), not for ordinary status changes.
- Per-type required fields cannot be database constraints because the block
  type is a data entity; they are enforced in serializer/service and
  re-checked at publish time. `access_level`, `status` and `source_type`
  controlled values get `TextChoices` plus DB `CheckConstraint`s.

### 9. API contract, permissions, pagination and throttling

- Public read endpoints declare `AllowAny` explicitly because the global DRF
  default is `IsAuthenticated`: subjects/sections/topics catalog and search are
  public; the topic content endpoint composes the access policy.
- `demo availability` is the boolean `has_demo_preview` (a published
  `is_demo_preview` child exists) next to `access_level`.
- Page-number pagination, default 20, maximum 100, matching spec 004.
- Named scoped throttle rates for the public catalog, topic content and search;
  429 is `THROTTLED` through the existing envelope.
- 422 responses (`INVALID_RELATION`, `VALIDATION_ERROR`) are raised as explicit
  `APIError`, because DRF serializer validation otherwise maps to 400.
- Every endpoint is documented in OpenAPI with its permission and error codes.
- Integration/Flashcard/Quiz surfaces are out of scope for 002 and stay with
  specs 004/003.

## Rejected alternatives

- Dropping image blocks from 002: contradicts ADR 0008 and spec 002 AC5.
- Moving media (004) before content: spec 004 depends on 002 content entities.
- Implementing `Plan`/`Subscription` models now or inventing an entitlement
  source/role bypass: the subscriptions feature is explicitly out of scope and
  the paywall contract must stay honest.
- Fake "always true/always false with a TODO" policy without a documented
  contract: the deny-by-default result is documented behavior, and the policy
  seam is the only import path allowed by the architecture.
- `ContentBlock.media` `RESTRICT`/`CASCADE`: contradicts the documented media
  repair edge case and would couple content deletion to storage lifecycle.
- Always-200 anonymous free/paid content with an empty list: deletes the accepted
  401 error row with no source-backed replacement.
- `UNIQUE(parent, position)` removed plus a `(position, id)` tiebreak only: would
  leave the spec's `CONTENT_CONFLICT` duplicate-position error without a
  trigger.
- Per-parent slug uniqueness: narrower contract than needed while public slug
  URLs are deferred; global uniqueness is reversible by dropping a constraint.
- Adding an HTML sanitizer dependency: not needed to satisfy "rejected or
  sanitized away" and forbidden without a concrete need.
- Human product gate for this feature: every gap was resolvable from a
  higher-priority accepted source; the delegated policy explicitly allows the
  manager to record and proceed.

## Residual risk

- Until the subscriptions feature ships, `paid` content is authorable but
  unreadable by everyone; AC3's entitled-allow row and US2.4 are deferred.
- AC9/US3.3 media URLs ship in spec 004; 002 proves only the FK reference and
  absence of storage secrets.
- 002's `MediaFile` rows are unverified metadata; if spec 004 changes the field
  set, a forward migration is required.
- The anonymous free/paid response is state-dependent (200 preview vs 401), so
  clients must read 401 on that endpoint as "no preview available".
- Global slug uniqueness and the `(parent, position)` constraint are recorded
  narrowing/closure of open items; later changes need a data migration.
- Django Admin sits outside the REST permission surface; the content permission
  hook plus service validation is the control.
- `ContentBlockType` seeding uses an idempotent data migration.
- AC4 (anonymous never creates learning state) is vacuous in 002 and belongs to
  spec 003.

## State transition and validation/rollback consequence

With this record and the focused spec amendments written, the workflow advances
`SPEC_REVIEW` → `READY_FOR_PLAN`; the manager may create
`feature/002-content-catalog-access` and produce plan/tasks before coding.
Implementation must prove: catalog visibility and no body leakage, demo-preview
filtering, the access matrix (deny path real, allow path through the policy
seam), publish validation, raw-HTML rejection, ordering/slug determinism,
cascade deletion and sibling preservation, search/pagination, permissions and
OpenAPI; then run the full AGENTS validation suite. If a source conflict,
security invariant or migration-compatibility issue appears, stop the affected
change, record the evidence and return `BLOCKED`. Migrations are forward-only;
a failed implementation is reverted on the unpushed feature branch, never by
rewriting applied migration history.

## Final review verdicts

- DeepSeek spec-reviewer: `NEEDS_HUMAN_REVIEW` — every listed blocker is
  resolvable by this record; the governance objection is answered by the
  delegated policy text, so no human gate remains.
- Luna watchdog: `BLOCKED` on the stale PROJECT_STATE gate (satisfied: 001 is
  merged) and the Draft/TBD status (satisfied: this record plus spec
  amendments); `RESOLVED` on all technical questions as adopted.
- DeepSeek architect: `READY` conditional on this record and the spec
  amendments, both now written.