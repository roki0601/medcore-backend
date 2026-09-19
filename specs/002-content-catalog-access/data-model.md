# Data model: Content catalog and Topic access

**Feature**: `002-content-catalog-access`  
**Date**: 2026-09-19  
**Source**: `specs/002-content-catalog-access/spec.md` and the
[delegated review](../../.omp/decisions/2026-09-19-002-content-catalog-access-quorum.md)

All IDs use `BigAutoField`. All timestamps are timezone-aware UTC. Every
`created_at`/`updated_at` uses `auto_now_add`/`auto_now`.

## media.MediaFile

FK target only; upload, access URL and storage adapter are spec 004.

| Field | Type | Rules |
|---|---|---|
| `storage_key` | `CharField(512)` | required, opaque provider key, never serialized |
| `original_name` | `CharField(255)` | blank allowed |
| `mime_type` | `CharField(127)` | required |
| `size_bytes` | `BigIntegerField` | required, `>= 0` |
| `checksum` | `CharField(128)` | blank allowed |
| `visibility` | `CharField(choices)` | `public` \| `protected`, default `protected` |
| `created_at`/`updated_at` | `DateTimeField` | UTC |

Constraints: `CheckConstraint(size_bytes >= 0)`, `CheckConstraint(visibility in
('public','protected'))`, unique `storage_key`.

## content.Subject

| Field | Type | Rules |
|---|---|---|
| `title` | `CharField(255)` | required, non-blank |
| `description` | `TextField` | blank allowed |
| `slug` | `SlugField(255)` | generated, unique |
| `position` | `PositiveIntegerField` | required, deterministic default |
| `created_at`/`updated_at` | `DateTimeField` | UTC |

Ordering: `(position, id)`.

## content.Section

| Field | Type | Rules |
|---|---|---|
| `subject` | `FK(Subject)` | required, `PROTECT` |
| `title` | `CharField(255)` | required, non-blank |
| `description` | `TextField` | blank allowed |
| `slug` | `SlugField(255)` | generated, unique |
| `position` | `PositiveIntegerField` | required, deterministic default |
| `created_at`/`updated_at` | `DateTimeField` | UTC |

Constraints: `UniqueConstraint(subject, position)`.
Ordering: `(position, id)`.

## content.Topic

| Field | Type | Rules |
|---|---|---|
| `section` | `FK(Section)` | required, `PROTECT` |
| `title` | `CharField(255)` | required, non-blank |
| `description` | `TextField` | blank allowed |
| `slug` | `SlugField(255)` | generated, unique |
| `position` | `PositiveIntegerField` | required, deterministic default |
| `status` | `CharField(choices)` | `draft` \| `published`, default `draft` |
| `access_level` | `CharField(choices)` | `demo` \| `free` \| `paid`, default `demo` |
| `created_at`/`updated_at` | `DateTimeField` | UTC |

Constraints: `UniqueConstraint(section, position)`,
`CheckConstraint(status in ('draft','published'))`,
`CheckConstraint(access_level in ('demo','free','paid'))`.
Ordering: `(position, id)`.

## content.ContentBlockType

| Field | Type | Rules |
|---|---|---|
| `key` | `SlugField(64)` | unique, seeded `markdown`/`image`/`callout` |
| `title` | `CharField(127)` | required display name |
| `active` | `BooleanField` | default `True` |

Seeded by an idempotent data migration (`get_or_create` on `key`).

## content.ContentBlock

| Field | Type | Rules |
|---|---|---|
| `topic` | `FK(Topic)` | required, `CASCADE` |
| `block_type` | `FK(ContentBlockType)` | required, `PROTECT` |
| `position` | `PositiveIntegerField` | required, deterministic default |
| `status` | `CharField(choices)` | `draft` \| `generated` \| `reviewed` \| `published` |
| `is_demo_preview` | `BooleanField` | default `False` |
| `markdown_body` | `TextField` | blank allowed; required for markdown/callout at publish |
| `media` | `FK(MediaFile)` | nullable, `SET_NULL`; required for image at publish |
| `caption` | `CharField(255)` | blank allowed |
| `reviewed_by` | `FK(users.User)` | nullable, `SET_NULL` |
| `published_at` | `DateTimeField` | nullable, server-assigned |
| `created_at`/`updated_at` | `DateTimeField` | UTC |

Constraints: `UniqueConstraint(topic, position)`,
`CheckConstraint(status in ('draft','generated','reviewed','published'))`.
Ordering: `(position, id)`.

Per-type required fields cannot be a database constraint because the block type
is a data row; they are enforced in the serializer/service and re-checked at
publish time.

## content.Source

| Field | Type | Rules |
|---|---|---|
| `title` | `CharField(255)` | required, non-blank |
| `source_type` | `CharField(choices)` | `textbook` \| `presentation` \| `article` \| `website` \| `guideline` \| `other` |
| `author` | `CharField(255)` | blank allowed |
| `year` | `PositiveSmallIntegerField` | nullable |
| `url` | `URLField(500)` | blank allowed |
| `note` | `TextField` | blank allowed |
| `topics` | `M2M(Topic)` | through table CASCADE |
| `content_blocks` | `M2M(ContentBlock)` | through table CASCADE |
| `created_at`/`updated_at` | `DateTimeField` | UTC |

Constraint: `CheckConstraint(source_type in (...))`.

## Deletion matrix

| Relation | on_delete | Rationale |
|---|---|---|
| `ContentBlock.topic` | `CASCADE` | Topic aggregate owns its blocks |
| `Topic.section` | `PROTECT` | no implicit mass deletion of topics |
| `Section.subject` | `PROTECT` | no implicit mass deletion of sections |
| `ContentBlock.block_type` | `PROTECT` | retire via `active`, never delete types |
| `ContentBlock.media` | `SET_NULL` | media repair path; publish re-checks |
| `ContentBlock.reviewed_by` | `SET_NULL` | 001 hard-deletes User; content survives |
| `Source.topics`/`Source.content_blocks` | `CASCADE` | links only, never content |
| learning → Topic/Section | `CASCADE` (spec 003) | declared cross-domain contract |

## Slug and position rules

- Slug source = `slugify(title)`; if empty, fall back to a stable derived token;
  collisions get `-2`, `-3`, … until free. Unique per model.
- Position omitted → `max(position) + 1` for the parent, computed with a
  `select_for_update` lock on the parent row inside the service transaction.
  Explicit duplicate → `IntegrityError` surfaced as 409 `CONTENT_CONFLICT`.

## Status transitions

- Any of the four workflow statuses may be set by editor/admin (not a linear
  state machine); manual content may be created `published`.
- `published_at` is set to `timezone.now()` when the status becomes `published`
  and cleared when it leaves `published`; never client-supplied.
- 409 `INVALID_CONTENT_STATE` is returned for publish-time precondition
  failures: markdown/callout without body, image without media.