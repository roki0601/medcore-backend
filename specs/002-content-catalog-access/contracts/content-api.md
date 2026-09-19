# API contract: Content catalog and Topic access

**Feature**: `002-content-catalog-access`  
**Base**: `/api/v1/`  
**Auth**: anonymous allowed on catalog and search; Topic content composes the
access policy. Global DRF default is `IsAuthenticated`, so public endpoints set
`AllowAny` explicitly.

All responses use the `{code, detail, fields}` error envelope for failures.
List responses use standard DRF page-number pagination
(`count`, `next`, `previous`, `results`), default page size 20, maximum 100.

## GET /api/v1/subjects/

Public. Paginated list of subjects ordered by `(position, id)`.

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {"id": 1, "title": "Pharmacology", "description": "", "slug": "pharmacology", "position": 1}
  ]
}
```

## GET /api/v1/subjects/{id}/

Public. Subject detail, `404 RESOURCE_NOT_FOUND` when missing.

## GET /api/v1/sections/{id}/

Public. Section detail.

```json
{"id": 4, "subject": 1, "title": "Antibiotics", "description": "", "slug": "antibiotics", "position": 2}
```

## GET /api/v1/topics/

Public. Paginated list of **published** topics ordered by `(position, id)`.
Optional query filters: `section_id`, `subject_id`. Unknown/invalid ids return
`422 INVALID_RELATION`.

```json
{
  "count": 1,
  "results": [
    {
      "id": 9,
      "section": 4,
      "subject": 1,
      "title": "Beta-lactams",
      "description": "",
      "slug": "beta-lactams",
      "position": 1,
      "status": "published",
      "access_level": "free",
      "has_demo_preview": true
    }
  ]
}
```

`has_demo_preview` is true when at least one published `is_demo_preview` block
exists. Draft topics are absent from the catalog.

## GET /api/v1/topics/{id}/

Public. Published topic detail with the same body as a list item. Draft,
generated or reviewed topics return `404 RESOURCE_NOT_FOUND`. The response never
contains block bodies or storage keys.

## GET /api/v1/topics/{id}/content/

Access-policed. Returns ordered published blocks the actor may read.

Decision table:

| Topic `access_level` | actor | result |
|---|---|---|
| `demo` | anonymous or authenticated | 200, all published blocks |
| `free` | authenticated | 200, all published blocks |
| `free`/`paid` | anonymous, ≥1 published `is_demo_preview` block | 200, exactly those blocks |
| `free`/`paid` | anonymous, no published demo preview | 401 `AUTHENTICATION_REQUIRED` |
| `paid` | authenticated without entitlement | 403 `TOPIC_ENTITLEMENT_REQUIRED` |
| `paid` | authenticated with entitlement | 200, all published blocks |
| any | topic not published | 404 `RESOURCE_NOT_FOUND` |

```json
{
  "topic": {
    "id": 9, "section": 4, "subject": 1, "title": "Beta-lactams",
    "description": "", "slug": "beta-lactams", "position": 1,
    "status": "published", "access_level": "free", "has_demo_preview": true
  },
  "access": {"level": "free", "full_access": true, "is_demo_preview": false},
  "sources": [
    {"id": 2, "title": "Guideline", "source_type": "guideline",
     "author": "", "year": 2024, "url": "https://example.org", "note": ""}
  ],
  "blocks": [
    {
      "id": 31,
      "block_type": {"key": "markdown", "title": "Markdown"},
      "position": 1,
      "status": "published",
      "is_demo_preview": true,
      "caption": "",
      "markdown_body": "# Theory",
      "media": null,
      "published_at": "2026-09-19T06:00:00+05:00",
      "sources": []
    },
    {
      "id": 32,
      "block_type": {"key": "image", "title": "Image"},
      "position": 2,
      "status": "published",
      "is_demo_preview": false,
      "caption": "Structure",
      "markdown_body": null,
      "media": {"id": 5, "mime_type": "image/png",
                "original_name": "structure.png", "visibility": "protected"},
      "published_at": "2026-09-19T06:00:00+05:00",
      "sources": []
    }
  ]
}
```

Rules:

- `markdown_body` is present only for markdown/callout blocks; `media` is present
  only for image blocks. `storage_key` is never serialized.
- Signed media URLs are delivered by spec 004; 002 returns the reference only.
- A child `is_demo_preview` marker never widens access beyond the Topic level.
- Only `published` blocks are returned; `draft`/`generated`/`reviewed` are
  invisible to user-facing reads.

## GET /api/v1/search/?q=&subject_id=&section_id=&page=

Public. Case-insensitive title search over Subject, Section and Topic.
`q` shorter than 1 character returns an empty result page. Optional
`subject_id`/`section_id` filters; invalid ids return `422 INVALID_RELATION`.
Topics are matched only when published; subjects and sections are always
matched. Results are grouped `subject` → `section` → `topic`, each ordered by
`(position, id)`, and paginated.

```json
{
  "count": 2,
  "results": [
    {"type": "subject", "id": 1, "title": "Pharmacology",
     "subject_id": 1, "section_id": null, "access_level": null,
     "has_demo_preview": null},
    {"type": "topic", "id": 9, "title": "Beta-lactams",
     "subject_id": 1, "section_id": 4, "access_level": "free",
     "has_demo_preview": true}
  ]
}
```

Body search and ranking are out of scope.

## Throttling

Scoped rates (shared Redis counters):

| Scope | Endpoints | Rate |
|---|---|---|
| `catalog` | subjects/sections/topics reads | `120/min` |
| `content_read` | `topics/{id}/content/` | `60/min` |
| `search` | `search/` | `60/min` |

Throttled requests return 429 `THROTTLED`.

## Errors

| Condition | HTTP | Code |
|---|---:|---|
| missing/invalid resource or unpublished in user API | 404 | `RESOURCE_NOT_FOUND` |
| anonymous full body without preview | 401 | `AUTHENTICATION_REQUIRED` |
| authenticated paid without entitlement | 403 | `TOPIC_ENTITLEMENT_REQUIRED` |
| invalid filter/parent relation | 422 | `INVALID_RELATION` |
| invalid payload | 422 | `VALIDATION_ERROR` |
| duplicate slug/position | 409 | `CONTENT_CONFLICT` |
| publish precondition failure | 409 | `INVALID_CONTENT_STATE` |
| rate limit | 429 | `THROTTLED` |

## OpenAPI

Every endpoint is annotated with drf-spectacular: permission, parameters,
response serializer and error responses. The catalog/content/search paths must
appear in `/api/v1/schema/`.