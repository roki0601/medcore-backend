# Data model: Synchronous content API and protected media

**Feature**: `004-content-api-media`
**Date**: 2026-09-19
**Source**: `specs/004-content-api-media/spec.md` and the
[delegated review](../../.omp/decisions/2026-09-19-004-content-api-media-review.md)

All IDs use `BigAutoField`. All timestamps are timezone-aware UTC. Every
`created_at`/`updated_at` uses `auto_now_add`/`auto_now`.

## Changes to entities shipped by feature 002

Every existing content entity that is addressable through the integration API
gains one nullable identity field:

| Model | Added field | Rules |
|---|---|---|
| `Subject` | `external_id` | `CharField(255)`, nullable, unique per model |
| `Section` | `external_id` | same |
| `Topic` | `external_id` | same |
| `ContentBlock` | `external_id` | same |
| `Source` | `external_id` | same |

No other 002 field changes. `ContentBlock.media` keeps
`on_delete=SET_NULL`; the published-reference protection is an application guard
(see "Media deletion guard").

`Source` gains two M2M relations that the accepted decision register already
declares (`0004:40`):

| Field | Type | Rules |
|---|---|---|
| `flashcards` | `M2M(Flashcard)` | through table CASCADE, links only |
| `questions` | `M2M(QuizQuestion)` | through table CASCADE, links only |

## content.Flashcard

| Field | Type | Rules |
|---|---|---|
| `topic` | `FK(Topic)` | required, `CASCADE` |
| `question` | `TextField` | required, non-blank |
| `answer` | `TextField` | required, non-blank |
| `position` | `PositiveIntegerField` | deterministic default |
| `external_id` | `CharField(255)` | nullable, unique |
| `created_at`/`updated_at` | `DateTimeField` | UTC |

Constraints: `UniqueConstraint(topic, position)`. Ordering `(position, id)`.
No status field: visibility follows the Topic.

## content.Quiz

| Field | Type | Rules |
|---|---|---|
| `topic` | `FK(Topic)` | required, `CASCADE` |
| `title` | `CharField(255)` | required, non-blank |
| `description` | `TextField` | blank allowed |
| `position` | `PositiveIntegerField` | deterministic default |
| `external_id` | `CharField(255)` | nullable, unique |
| `created_at`/`updated_at` | `DateTimeField` | UTC |

Constraints: `UniqueConstraint(topic, position)`. Ordering `(position, id)`.

## content.QuizQuestion

| Field | Type | Rules |
|---|---|---|
| `quiz` | `FK(Quiz)` | required, `CASCADE` |
| `text` | `TextField` | required, non-blank |
| `position` | `PositiveIntegerField` | deterministic default |
| `created_at`/`updated_at` | `DateTimeField` | UTC |

Constraints: `UniqueConstraint(quiz, position)`. Ordering `(position, id)`.

## content.QuizAnswer

| Field | Type | Rules |
|---|---|---|
| `question` | `FK(QuizQuestion)` | required, `CASCADE` |
| `text` | `TextField` | required, non-blank |
| `is_correct` | `BooleanField` | default `False` |
| `position` | `PositiveIntegerField` | deterministic default |
| `created_at`/`updated_at` | `DateTimeField` | UTC |

Constraints: `UniqueConstraint(question, position)`. Ordering `(position, id)`.

Aggregate invariants enforced in the write service (not expressible as a single
database constraint because they span rows): a quiz keeps at least one question,
each question keeps at least two answers and at least one correct answer. The
unique `(parent, position)` constraints and the `CASCADE` relations are the
database backstop.

## Deletion matrix (extended)

| Relation | on_delete | Rationale |
|---|---|---|
| `Flashcard.topic` | `CASCADE` | Topic aggregate owns its cards |
| `Quiz.topic` | `CASCADE` | Topic aggregate owns its quizzes |
| `QuizQuestion.quiz` | `CASCADE` | quiz aggregate owns its questions |
| `QuizAnswer.question` | `CASCADE` | question owns its answers |
| `ContentBlock.media` | `SET_NULL` | unchanged; guarded in the delete service |
| `Source.flashcards` / `Source.questions` | `CASCADE` | links only, never content |
| learning → Topic/Section/Quiz | `CASCADE` (spec 003) | declared cross-domain contract |

## Media deletion guard

`ContentBlock.media` stays `SET_NULL`, so the database does not reject media
deletion. The rejection required by the spec is an application guard:

1. `apps.media.services.delete_media_file` opens one transaction and locks the
   `MediaFile` row with `select_for_update`.
2. It calls the content-owned guard
   (`settings.MEDIA_DELETE_GUARD_PROVIDER`, default
   `apps.content.media_policy.guard_media_deletion`), which locks the published
   content blocks referencing the file and raises 409 `CONTENT_CONFLICT` when any
   exist.
3. Otherwise the row is deleted; unpublished references detach through
   `SET_NULL`.
4. Storage cleanup is registered with `transaction.on_commit` and a failure is
   logged, never rolled back.

Lock order is always `MediaFile` row first, then content rows.
`apps.content.services.publish_content_block` therefore locks the media rows
referenced by the block first (through the `content_blocks` reverse relation),
then the block row, and raises 409 `CONTENT_CONFLICT` if the locked block's
`media_id` no longer matches the locked set. This makes publish and delete
serialize on the same row and removes the TOCTOU window.

## Media storage configuration

| Setting | Default | Meaning |
|---|---|---|
| `MEDIA_STORAGE_BACKEND` | `local` | `local` \| `s3` |
| `MEDIA_STORAGE_ROOT` | `<BASE_DIR>/media-storage` | local object root |
| `MEDIA_S3_ENDPOINT_URL` | `""` | S3-compatible endpoint |
| `MEDIA_S3_BUCKET` | `""` | bucket name |
| `MEDIA_S3_REGION` | `us-east-1` | region |
| `MEDIA_S3_ACCESS_KEY` / `MEDIA_S3_SECRET_KEY` | `""` | credentials |
| `MEDIA_S3_ADDRESSING_STYLE` | `path` | path \| virtual |
| `MEDIA_ALLOWED_MIME_TYPES` | png/jpeg/webp/gif | upload allow-list |
| `MEDIA_MAX_UPLOAD_BYTES` | 5 MiB | upload limit |
| `MEDIA_UPLOAD_URL_TTL` | 600 s | upload contract expiry |
| `MEDIA_ACCESS_URL_TTL` | 600 s | signed read URL expiry |
| `MEDIA_UPLOAD_TOKEN_SALT` / `MEDIA_ACCESS_TOKEN_SALT` | fixed strings | capability token salts |
| `MEDIA_ACCESS_POLICY_PROVIDER` | `apps.content.media_policy.decide_media_access` | content-owned access decision |
| `MEDIA_DELETE_GUARD_PROVIDER` | `apps.content.media_policy.guard_media_deletion` | content-owned delete guard |
| `MEDCORE_CONTENT_API_KEY` | `""` | integration secret; empty denies all |

Local objects are stored at `<MEDIA_STORAGE_ROOT>/<storage_key>` with a sidecar
`<storage_key>.meta` holding the verified content type, so `verify_object` can
report size and MIME without trusting the database row alone.

`storage_key` is generated server-side (opaque, no client input) and is never
serialized by any endpoint.

## Identity and position rules

- `external_id` is optional on the seven top-level CRUD entities, unique per
  model (one configured integration namespace), immutable once established.
- Position rules reuse feature 002: omitted → `max(position) + 1` for the parent
  under a `select_for_update` lock on the parent row inside the service
  transaction; an explicit duplicate is 409 `CONTENT_CONFLICT`.
- Quiz children use the same position rules inside the quiz write transaction;
  nested items are matched by `id` and never regenerated.
