# Research: Synchronous content API and protected media

**Feature**: `004-content-api-media`
**Date**: 2026-09-19
**Decision record**: [delegated review](../../.omp/decisions/2026-09-19-004-content-api-media-review.md)

## Findings

- **Integration contract**: ADR 0008 fixes synchronous REST CRUD with one
  integration key, no import file, no `ImportJob`, no Celery and no automatic
  deletion of missing objects. Spec 004 adds `external_id` upsert, an explicit
  delete target and a strict schema. No source asks for bulk endpoints or a
  second credential, so none is added.
- **Content entities**: `content` owns Flashcard, Quiz, QuizQuestion,
  QuizAnswer and Source (`domain-model.md`, `target-architecture.md`). Spec 003
  consumes them for learning state and requires stable question/answer IDs for
  attempts, so the quiz aggregate is written by identity-preserving upsert and
  children are never deleted. A question may have one or several correct answers
  (ADR 0008); the stale "one correct answer" line in `domain-model.md` was
  corrected traceably.
- **Answer minima**: the scoring formula in spec 003 divides by
  `correct_answer_count` and averages question scores, so a question needs at
  least one correct answer and a quiz needs at least one question for the score
  to be defined. Both are enforced at write time. "At least one quiz per Topic"
  is not in any source and is not enforced.
- **Storage**: ADR 0008 requires object storage with short-lived signed URLs for
  private/paid media but does not select a provider; spec 004 keeps the adapter
  provider-neutral and the provider a deployment decision. The adapter is
  therefore shipped with a local backend for dev/test (refused outside `DEBUG`)
  and an S3-compatible backend (MinIO/AWS/any S3 API) whose SDK is an optional
  dependency group. No object-storage service is added to `compose.yaml`.
- **Upload handshake**: the spec allows a presigned URL or an equivalent
  controlled upload contract, and requires verification before the media becomes
  usable. The local backend uses capability-token endpoints; the S3 backend uses
  presigned `PUT`; both verify declared size (and checksum when supplied) before
  a read URL is issued.
- **Media access**: `media` must not import `content`, yet the access decision is
  content's (Topic policy, demo preview, entitlement through
  `subscriptions.policy`). The two needed decisions therefore arrive as
  fail-closed settings providers owned by `apps.content.media_policy`, keeping
  route ownership in `apps/media`.
- **Media deletion**: 002 recorded `SET_NULL` for `ContentBlock.media` and
  rejected `PROTECT`/`RESTRICT`; spec 004 requires deletion of a referenced
  published file to be rejected or repaired first. The recorded choice is kept
  and the rejection is an application guard executed inside the delete
  transaction, with the publish path locking the same media row so the two
  operations serialize.
- **Error contract**: the project envelope `{code, detail, fields}` and the HTTP
  table from `conventions.md` already cover every condition; DRF maps serializer
  validation to `INVALID_REQUEST/400`, so 422 responses are raised as explicit
  `APIError`, exactly as feature 002 did.
- **Permissions**: the global DRF default is `IsAuthenticated` and only the JWT
  authenticator exists today. The integration credential therefore needs its own
  authenticator, a non-User principal and route-scoped permissions; user-facing
  routes must never read the header.

## Rejected alternatives

- Selecting a concrete provider or adding MinIO to `compose.yaml`.
- Making the S3 SDK a required dependency.
- `on_delete=PROTECT` on `ContentBlock.media` (supersedes 002's accepted record).
- A reverse `media → content` import for the access decision or the delete guard.
- Regenerating or deleting quiz children on update.
- A one-correct-answer shortcut.
- Enforcing at least one quiz per Topic.
