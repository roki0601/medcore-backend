# Delegated review decision: synchronous content API and protected media

- Feature: `004-content-api-media`
- Workflow state: `SPEC_REVIEW` → `DELIBERATING` → `READY_FOR_PLAN`
- Decision status: accepted for this feature implementation
- Decision time: 2026-09-19T07:48:46Z
- Review roles and model identifiers:
  - DeepSeek manager/spec review (source-backed review performed by the manager):
    `openrouter/deepseek/deepseek-v4.1-flash` (`@plan`)
  - Luna `watchdog` escalation: `openai-codex/gpt-5.6-luna` (thinking level `high`),
    two bounded rounds

## Question and affected workflow state

Spec `specs/004-content-api-media/spec.md` is a Draft, High-risk spec and cannot
advance to planning until the delegated review closes its gaps and its internal
contradictions. The open items were: the concrete object-storage provider (TBD in
the spec, `docs/architecture/open-questions.md` §12 and
`target-architecture.md`), the upload/access handshake the spec leaves to
"implementation planning", the integration-key authentication surface, the
question/answer write contract (the spec lists `Question`/`Answer` as content
entities but publishes no routes for them), the `external_id` upsert semantics,
the Flashcard/Quiz field sets and validation minima, the media
`access-url` authorization rule, media deletion versus a published image block,
and one stale `docs/architecture/domain-model.md` invariant.

## Preflight evidence

Three-repository preflight before the feature branch, all worktrees clean and all
fast-forward:

| Repository | Branch | HEAD |
|---|---|---|
| `medcore-docs` | `main` | `0b1d51c` |
| `medcore-backend` | `main` | `d7a9584` |
| `medcore-frontend` | `main` | `db3473d` |

`PROJECT_STATE.md` still said feature 002 needed a manual merge; PR
https://github.com/roki0601/medcore-backend/pull/5 is `MERGED` and `main` at
`d7a9584` is its merge commit, so that gate is satisfied and stale.
`PROJECT_STATE.md` is refreshed by this run. Branch
`feature/004-content-api-media` was created from `d7a9584`.

## Authoritative evidence

- `AGENTS.md:15-24,27-32,71-85,107-127` — source precedence, delegated spec
  approval, ownership guardrails, migration rules.
- `.omp/AUTONOMOUS_REVIEW.md:11-14,47-83,85-102` — manager performs the
  source-backed review, at most two bounded escalation rounds, every escalation
  and material interpretation gets a record.
- `specs/004-content-api-media/spec.md` (whole file) — scope, business rules,
  invariants, data model, API, permissions, validation, errors, transactions,
  concurrency, acceptance criteria, open questions.
- `specs/004-content-api-media/checklists/requirements.md` — readiness checklist.
- `.omp/decisions/2026-09-19-002-content-catalog-access-quorum.md:141-167,250-254,300-320`
  — accepted 002 resolutions this feature inherits: minimal `MediaFile`, the
  `subscriptions.policy` seam, numeric-ID CRUD deferred slugs, `SET_NULL` on
  `ContentBlock.media` with a publish-time re-check, and the learning cascade
  carry-forward.
- `specs/002-content-catalog-access/spec.md:245-254,290-297,369-383,436-438` —
  the MediaFile field set, `SET_NULL`, the repair-before-publication edge case,
  anonymous preview behavior and the delegation of URL issuance to 004.
- `specs/003-learning-state/spec.md:100-141,263-268,295-301,339-340` — content
  owns Flashcard/Quiz/Question/Answer; multiple quizzes; one-or-many correct
  answers; the partial-score formula with `correct_answer_count`; stable
  question/answer IDs for an attempt; "incompatible content changes are blocked
  or require a new attempt policy".
- `../medcore-docs/decisions/0008-mvp-auth-content-and-integration-contract.md:46-65,84-109`
  — synchronous content API with one integration key, no ImportJob/Celery, one
  or several correct answers, simple card scheduling, object storage with
  short-lived signed URLs, provider explicitly not selected.
- `../medcore-docs/decisions/0004-mvp-decision-register.md:33-41,51-53,71-82,95-99`
  — physical deletion, Topic cascade to blocks/cards/quizzes, Source M2M scope
  (Topic, ContentBlock, Flashcard, QuizQuestion), object storage confirmed with
  the provider unfixed, `Source` relations optional.
- `../medcore-docs/decisions/0006-anonymous-demo-content.md:19-30` and
  `0007-content-access-model.md:19-64` — anonymous demo/preview scope, the Topic
  access boundary, child demo-preview marker.
- `docs/architecture/target-architecture.md:67-118,145-181,198-231` — app
  ownership, allowed dependency direction (`content → media`,
  `content.application → subscriptions.policy`, media never imports a business
  domain), thin views, services/selectors, transaction boundaries, provider TBD
  and no async infrastructure.
- `docs/architecture/conventions.md:34-74,76-109,132-156` — error envelope,
  HTTP table, validation layers, transaction/constraint and physical-deletion
  rules.
- `docs/architecture/domain-model.md:36-41,115-120,159-188` — cardinalities,
  Quiz semantics and lifecycle rules (one stale invariant line, see §4).
- Existing code: `apps/content/{models,services,selectors,access,serializers,views,urls,admin}.py`,
  `apps/media/{models,admin}.py`, `apps/common/{exceptions,pagination}.py`,
  `apps/users/{models,authentication,throttles}.py`,
  `apps/subscriptions/policy.py`, `config/settings/{base,local}.py`,
  `config/urls.py`, `pyproject.toml`, `compose.yaml`, `.env.example`,
  `.github/workflows/ci.yml`, `apps/content/tests/*` (92 tests green before this
  feature).

## Manager review findings (the gaps the spec leaves open)

1. Object-storage provider and the upload/access handshake are `TBD`; the spec
   requires a provider-neutral adapter and defers the concrete provider, while
   ADR 0008 requires object storage in production.
2. The integration key has no defined route scope, no defined interaction with a
   simultaneously presented user JWT, and the error table's
   `INTEGRATION_KEY_INVALID`/`INTEGRATION_SCOPE_FORBIDDEN` rows have no explicit
   trigger.
3. `Question`/`Answer` are declared content entities but have no routes; the
   child write contract (identity, deletion, minima) is unstated, and spec 003
   requires stable question/answer IDs for attempts.
4. `docs/architecture/domain-model.md` still claims "one correct QuizAnswer per
   QuizQuestion on MVP", which contradicts ADR 0008 and spec 003 (one or many).
5. Media deletion versus a published image block has no mechanism; an
   app-level check would force `media` to read content data, which the
   architecture forbids.
6. `external_id` scope, upsert status codes and mutation rules are unstated.
7. Flashcard/Quiz field sets and answer minima are unstated; a zero-question quiz
   would make spec 003's arithmetic-average score undefined; accepted 0004:40
   Source relations to Flashcard/QuizQuestion are missing from the plan.
8. `access-url` requires "normal user authentication" while the same spec allows
   anonymous public media — a direct contradiction.

## Luna escalation

Two bounded rounds were run (trigger 5: security/auth/permission/concurrency
change; trigger 4: source disagreement). Packet:
`local://004-spec-review-packet.md` (session-local), evidence paths and lines as
listed above.

### Round 1 verdicts

| Item | Verdict | Substance |
|---|---|---|
| 1 storage | `RESOLVED` | provider-neutral adapter, local implementation for dev/test only, production must refuse the local backend, S3-compatible not mandatory, no MinIO in compose, capability URL bound to operation + media id + method + expiry, never containing `storage_key` |
| 2 integration key | `RESOLVED` | marked routes only, wrong/empty key ⇒ hard 401 even with a valid JWT, separate non-User principal, `access-url` rejects the integration principal, user routes never read the header |
| 3 quiz children | `BLOCKED` | regenerating question/answer IDs conflicts with spec 003's stable-ID requirement; rule 7 does not authorize silent child deletion |
| 4 stale invariant | `RESOLVED` | follow ADR 0008 (one or many correct answers); fix the stale `domain-model.md` line traceably |
| 5 media deletion | `RESOLVED` with conditions | 409 for published references is coherent with `SET_NULL`, but the check must be race-safe and must not make `media` import `content` |
| 6 `external_id` | `RESOLVED` | per-model unique nullable identity, POST 201/200 upsert, PATCH to another owner 409, established identity is immutable |
| 7 content models | `RESOLVED` | mandatory Topic relations, no shuffle/status, ≥2 answers and ≥1 correct, no invented "quiz ≥1 per Topic", explicit zero-question policy, restore accepted Source relations |
| 8 `access-url` | `BLOCKED` | the spec contradicts itself: JWT-only under-grants anonymous public media; authorization must run before any storage call |
| overall | `BLOCKED` | items 3 and 8 unresolved |

### Round 2 verdicts

The manager submitted the resolutions below. Luna returned:

- item 8 — `RESOLVED` with the amendment fixed explicitly (authorization before
  `head_object`, `AllowAny` for public media, protected anonymous only through
  the 002 preview policy, otherwise 401/403);
- item 7 — `RESOLVED` (≥1 question, ≥2 answers, ≥1 correct, Source M2M, Topic
  stays 0..N);
- item 5 — `BLOCKED`: `on_delete=PROTECT` "directly supersedes an accepted
  decision" (002's record `:141-167` and `specs/002-.../spec.md:250-254,369-370`
  choose `SET_NULL` and reject `RESTRICT`/`PROTECT`); the remedy is either an
  explicitly accepted cross-feature decision with a 002 update, or keeping
  `SET_NULL` with race-safe orchestration;
- item 3 — `BLOCKED`: identity preservation helps, but omission-deletion can
  still remove a child that a future `QuizAttempt` references, and 004 cannot
  know about attempts; an explicit immutable-content/snapshot/FK policy is
  required before `READY_FOR_PLAN`;
- overall — `BLOCKED` on items 3 and 5.

### Deliberation and rebuttal (how the two blockers were closed)

The manager did not repeat the rejected proposals; it adopted the remedies Luna
named.

**Item 5 — `SET_NULL` is preserved; the guard is orchestrated from `content`.**
`ContentBlock.media` keeps `on_delete=SET_NULL`, so 002's accepted decision is
not superseded and no migration of that FK is needed. The published-reference
rejection is implemented in `apps/content/media_policy.py`
(`guard_media_deletion`) and reached from `apps/media` through a fail-closed,
settings-declared policy seam
(`MEDIA_DELETE_GUARD_PROVIDER = "apps.content.media_policy.guard_media_deletion"`,
resolved with `import_string`). `apps/media` therefore has no static import of
`content`; the seam mirrors the same inversion already required for
`access-url`. Race safety: the delete transaction locks the `MediaFile` row and
re-checks published references before deleting, and `publish_content_block`
takes the same `MediaFile` row lock when the block references media, so a
concurrent publish/delete serializes on one row and can never leave a published
image block detached. Storage cleanup runs in `transaction.on_commit`, failures
are logged and never roll back the committed database delete. The 002 publish
service therefore gains one additive row lock, and no 002 test or migration is
rewritten. This is Luna's option (b) "keep `SET_NULL` + race-safe orchestration".

**Item 3 — explicit immutable-content policy: children are never deleted.**
The quiz aggregate write upserts nested questions and answers by an optional
`id` (in place, ID preserved) and creates items without an `id`. Omission never
deletes: there is no child-deletion path in the content API at all, which is
consistent with spec 004's own route list (DELETE exists only for the seven
top-level resources) and with business rule 7 ("no automatic deletion is
inferred from an object missing in a later request"). A referenced question or
answer can therefore never dangle for a future attempt, which is exactly the
immutable-content policy Luna required, and spec 003 keeps ownership of the
aggregate-deletion policy it already declares
(`specs/003-learning-state/spec.md:339-340`). The same rule makes the
`external_id` identity immutable (§6).

Two bounded rounds are the documented budget, so no third round was run. Luna's
round-2 verdict and its remedy conditions are recorded verbatim above; both
blockers are closed by the remedies it named, not by re-argument, and the
residual governance note is carried in "Residual risk".

## Final decision

### 1. Storage boundary (provider-neutral adapter; provider stays a deployment decision)

- `apps/media/storage.py` defines the provider-neutral `StorageAdapter` contract:
  `create_upload_url`, `create_access_url`, `verify_object`, `delete_object`
  plus a `supports_controlled_upload` capability and, for adapters that route
  bytes through the backend, `write_object`/`read_object`.
- `LocalStorageAdapter` (files under `MEDIA_STORAGE_ROOT`, default
  `<BASE_DIR>/media-storage`) is the dev/test backend. Its upload contract is
  the controlled endpoint `PUT /api/v1/media/upload/{token}/` and its access
  contract is `GET /api/v1/media/file/{token}/`; both use
  `django.core.signing` capability tokens bound to operation, media id, HTTP
  method and expiry, never containing `storage_key`, and are never logged.
- `S3StorageAdapter` (S3-compatible: MinIO, AWS S3 or any S3 API) is selected by
  `MEDIA_STORAGE_BACKEND=s3` and returns presigned upload/access URLs. Its SDK
  (`boto3`) is an optional dependency group, not a required dependency; no
  object-storage service is added to `compose.yaml`.
- `MEDIA_STORAGE_BACKEND` defaults to `local`. A Django system check fails
  (`Error`) when the local backend is selected with `DEBUG=False`, so production
  fails closed instead of silently serving media from a non-object-storage
  backend.
- TTLs: `MEDIA_UPLOAD_URL_TTL` and `MEDIA_ACCESS_URL_TTL`, both 600 s.
- Allow-list `image/png`, `image/jpeg`, `image/webp`, `image/gif` and
  `MEDIA_MAX_UPLOAD_BYTES` (default 5 MiB); anything else is 422 `MEDIA_INVALID`.
- The concrete provider remains a deployment decision; the adapter interface is
  the extension point. No new infrastructure technology is introduced.

### 2. Integration key authentication

- `MEDCORE_CONTENT_API_KEY` (env, never persisted or logged; unset ⇒ every
  integration request is denied) compared with `secrets.compare_digest`.
- `apps/common/integration.py` owns `IntegrationKeyAuthentication`,
  `IntegrationClient` (a principal with no `User` attributes, role or
  `is_authenticated`), `HasIntegrationKey`, `IsContentAuthor` and
  `IsNotIntegrationClient`.
- The header `X-MedCore-Integration-Key` is read only by marked content/media
  routes. The integration authenticator runs before the JWT authenticator and
  hard-fails 401 `INTEGRATION_KEY_INVALID` when the header is present but wrong
  or empty, even alongside a valid JWT. An absent header falls through to the
  normal JWT path.
- Content authoring CRUD accepts JWT with `role in {editor, admin}` or the
  integration principal. User-facing views never accept the key; presenting it
  to `access-url` is 403 `INTEGRATION_SCOPE_FORBIDDEN`. The key never grants
  paid-content access and never bypasses Topic policy.
- `MediaFileAdmin` gets the same staff + `role in {editor, admin}` gate used by
  the content CMS.

### 3. Content CRUD surface and quiz aggregate

- `/api/v1/content/{subjects,sections,topics,blocks,flashcards,quizzes,sources}/`
  with `GET, POST` on the collection and `GET, PATCH, DELETE` on the detail,
  matching the spec's route list. DELETE takes an explicit id; a repeated DELETE
  returns 404 `RESOURCE_NOT_FOUND` after the first 204, and never touches
  siblings.
- Unknown JSON fields are rejected with 422 `VALIDATION_ERROR` (DRF ignores them
  by default, so a strict serializer base enforces it).
- `Flashcard(topic CASCADE, question, answer, position, external_id)`,
  `Quiz(topic CASCADE, title, description, position, external_id)`,
  `QuizQuestion(quiz CASCADE, text, position)`,
  `QuizAnswer(question CASCADE, text, is_correct, position)`, uniqueness on
  `(parent, position)`, ordering `(position, id)`, no persisted shuffle or
  status fields; visibility follows the Topic. `Source` gains the accepted
  optional M2M to `Flashcard` and `QuizQuestion` (`0004:40`).
- Quiz create/update is one aggregate write in one transaction: nested
  `questions[]` with `answers[]`, identity-preserving upsert by optional `id`,
  omission never deletes, validation ≥1 question, ≥2 answers, ≥1 correct answer,
  non-blank text, deterministic positions. This makes spec 003's
  `correct_answer_count` denominator and its arithmetic-average score
  well-defined and keeps question/answer IDs stable. Topic keeps 0..N quizzes.

### 4. `external_id` identity

Nullable, per-model unique on the seven top-level CRUD entities (one configured
integration namespace). `POST` with a known `external_id` updates that entity
and returns 200; otherwise it creates and returns 201. An established
`external_id` is immutable: `PATCH` that changes or clears it is 409
`EXTERNAL_ID_CONFLICT`, and a unique-constraint race maps to the same stable
409. Lookup and mutation happen inside the write transaction after full payload
validation.

### 5. Media API, access decisions and deletion

- `POST /api/v1/media/` creates metadata only (opaque server-generated
  `storage_key`, never serialized), `GET /api/v1/media/{id}/` reads it,
  `DELETE /api/v1/media/{id}/` deletes it, `GET /api/v1/media/{id}/upload-url/`
  issues the upload contract.
- `DELETE` locks the `MediaFile` row, asks the content-provided guard whether a
  published block references the file (409 `CONTENT_CONFLICT` if so, with
  "detach the reference first" as the repair path), deletes, and cleans storage
  in `transaction.on_commit` with the failure logged.
- `GET /api/v1/media/{id}/access-url/` is `AllowAny`. `public` media is signed
  for anonymous and authenticated actors alike (actor table, US3.1, ADR 0006/0007).
  `protected` media requires authorization that is evaluated strictly before any
  `head_object`/signing: anonymous receives 401 `AUTHENTICATION_REQUIRED` unless
  the file is referenced by a published block the anonymous actor may read under
  the 002 demo/preview rules, an authenticated actor without access receives 403
  `MEDIA_ACCESS_DENIED`, and the integration principal receives 403
  `INTEGRATION_SCOPE_FORBIDDEN`. Object metadata is verified before signing; a
  missing or mismatched object is 422 `MEDIA_INVALID` and never a URL.
- Upload verification: the declared `size_bytes` must match the uploaded byte
  count and the checksum when supplied; a mismatch leaves the object
  inaccessible. `storage_key` and provider credentials are never returned.
- `apps/content/media_policy.py` provides the two content-owned decisions
  (`decide_media_access`, `guard_media_deletion`) through the fail-closed
  settings seam described above, so `apps/media` keeps URL ownership and never
  imports content business code.

### 6. Documentation and carry-forward contracts

- `docs/architecture/domain-model.md` gets one traceable correction: a
  `QuizQuestion` may have one or several correct answers (ADR 0008), replacing
  the stale "one correct QuizAnswer per QuizQuestion" invariant. This record is
  the traceability reference.
- Spec 004 is amended to the contract above (status `Approved for
  implementation`); its open questions are closed as recorded here.
- Carry-forward: spec 003 owns the attempt-time policy for aggregate deletion
  (`QuizAttempt` cleanup and the incompatible-change rule) and the learning-owned
  `ON DELETE CASCADE` to Topic/Section; the subscriptions feature still owns the
  entitlement source behind `has_paid_content_entitlement`.

## Rejected alternatives

- Selecting a concrete object-storage provider or adding MinIO to
  `compose.yaml`: the spec and ADR 0008 leave the provider to deployment, and new
  infrastructure needs its own decision.
- Making the S3 SDK a required dependency: the provider is not selected, so the
  adapter stays optional and the local backend keeps the default path testable.
- JWT-only `access-url`: under-grants anonymous public media and contradicts the
  spec's own actor table and US3.1.
- `on_delete=PROTECT` on `ContentBlock.media`: supersedes 002's accepted
  `SET_NULL` decision and rejects deletion for draft references; kept as a
  rejected alternative.
- A reverse `media → content` import for the delete guard or the access
  decision: forbidden dependency direction.
- Regenerating question/answer IDs on update, or deleting omitted children:
  breaks spec 003's stable-ID requirement and business rule 7.
- A one-correct-answer shortcut: contradicts ADR 0008 and corrupts multi-answer
  partial scoring.
- Enforcing "at least one quiz per Topic": not present in any source and would
  turn optional content into required content.

## Residual risk

- The concrete object-storage provider is still not selected. Until an
  S3-compatible backend is configured, production refuses the local backend by
  system check, so production media upload requires the deployment decision; the
  S3 adapter is exercised with a stubbed client and a live local smoke test
  rather than a production bucket.
- Luna's round-2 verdict was `BLOCKED`; both blockers were closed by adopting the
  remedies it named (recorded above), and no third round was run because the
  policy allows two bounded rounds. A human reviewer may re-open items 3 and 5.
- Capability URLs for the local backend are bearer secrets with a short TTL; they
  must never be logged, and the local backend must not be used in production.
- The published-reference guard depends on the settings seam; a missing or
  mistyped provider path fails closed (deletion refused, protected media denied).
- `external_id` uniqueness is per model under a single configured namespace;
  multiple database-managed namespaces would need a composite identity
  constraint.
- `paid` media still cannot be served until the subscriptions feature supplies
  the entitlement source; the deny path is real and the allow path is proven
  through the policy seam.
- Slug-based public URLs, bulk endpoints, async import and media processing
  remain out of scope.

## State transition and validation/rollback consequence

With this record and the focused spec/architecture amendments written, the
workflow advances `SPEC_REVIEW` → `READY_FOR_PLAN`; the manager may produce
plan/tasks and then implement on `feature/004-content-api-media`. Implementation
must prove: integration key valid/invalid/missing and scope separation, strict
payload rejection, `external_id` upsert and conflict, aggregate quiz write with
stable IDs and answer minima, Topic cascade with sibling preservation, media
MIME/size/upload verification, public/protected/paid `access-url` behavior with
authorization before storage access, signed URL expiry, the published-reference
delete guard under concurrency, throttling, secret-safe logs and OpenAPI; then
run the full `AGENTS.md` validation suite. A source conflict, security invariant
or migration-compatibility issue stops the affected change and is recorded as
`BLOCKED`. Migrations are forward-only; a failed implementation is reverted on
the unpushed feature branch, never by rewriting applied migration history.

## Final review verdicts

- DeepSeek manager review: `READY_FOR_PLAN` after this record and the spec
  amendments; every gap resolved from a higher-priority source.
- Luna watchdog round 1: `BLOCKED` on items 3 and 8, `RESOLVED` on items 1, 2, 4,
  6, 7 and conditionally 5.
- Luna watchdog round 2: `BLOCKED` on items 3 and 5 (both closed here by the
  remedies Luna named), `RESOLVED` on items 7 and 8.

## Post-implementation review amendments (2026-09-19)

Two independent read-only reviews ran on the finished diff before delivery.

- DeepSeek `senior-reviewer`: `BLOCKED` on one defect with a single cause — the
  `MediaFile` row lock lived in `publish_content_block`, which no production path
  calls, while the reachable publish path (`save_content_block(status="published")`
  from the API and Django Admin) locked only the topic. A concurrent
  `DELETE /api/v1/media/{id}/` could therefore pass its guard and then detach a
  freshly published block through the `SET_NULL` cascade. Fixed by taking the
  media row lock in `save_content_block` before `_apply_status`, keeping the
  documented lock order, plus a regression test that gates the delete after the
  guard; the test fails when the lock is reverted. Non-blocking findings were
  also closed: `DoesNotExist` under the delete locks now maps to 404
  `RESOURCE_NOT_FOUND`, media OpenAPI coverage was added, and a pinned
  undocumented error message was replaced by code/state assertions.
- DeepSeek `security-reviewer`: `READY`, no exploitable defect; 5 low/informational
  findings. Closed: the declared 5 MiB upload limit was unreachable because
  Django's 2.5 MB `DATA_UPLOAD_MAX_MEMORY_SIZE` fired first (now derived from
  `MEDIA_MAX_UPLOAD_BYTES`, the receiver validates the token and the declared
  `Content-Length` before reading the body, and the S3 presign binds
  `ContentLength`); a second upload contract for an already uploaded object is
  refused with 409 `CONTENT_CONFLICT`; `MediaDetailView` and the capability
  download view got throttle scopes (`media_metadata`, `media_access`); the
  storage-cleanup warning logs the media id instead of the `storage_key`.
- Accepted residual risks recorded, not fixed: the local capability token travels
  in the URL path, so the deployment must exclude the two controlled prefixes
  from access logs; an S3-compatible presigned URL necessarily contains the
  object key, so the bucket must stay private; the S3 adapter has no live
  production bucket (verified against a throwaway MinIO instance instead).
- `docs/architecture/domain-model.md` gained the resolved quiz cardinalities
  (0..N Quiz per Topic, 1..N QuizQuestion, 2..N QuizAnswer) with this record as
  the traceability reference.

