# API contract: Synchronous content CRUD

**Feature**: `004-content-api-media`
**Base**: `/api/v1/`
**Auth**: integration key or editor/admin JWT on every route in this document.
All responses use the `{code, detail, fields}` error envelope.
List responses use DRF page-number pagination (default 20, maximum 100).

## Authentication

```
X-MedCore-Integration-Key: <MEDCORE_CONTENT_API_KEY>
```

- The integration authenticator runs before the JWT authenticator on these
  routes only.
- Header present but wrong or empty → 401 `INTEGRATION_KEY_INVALID`, even when a
  valid `Authorization: Bearer` token is also present.
- Header absent → normal JWT path. A user with `role in {editor, admin}`
  (active) may call these routes; any other authenticated user gets 403
  `PERMISSION_DENIED`.
- An unset `MEDCORE_CONTENT_API_KEY` denies every integration request.
- The integration principal is not a `User`; it cannot read user-facing
  endpoints and cannot bypass Topic access policy.

## Common write semantics

| Aspect | Contract |
|---|---|
| Unknown top-level JSON field | 422 `VALIDATION_ERROR`, `fields` names each unknown key |
| Unknown relation id (`subject`, `topic`, `block_type`, `media`, id lists) | 422 `INVALID_RELATION` |
| `position` omitted | `max(position) + 1` for the parent, assigned under a parent row lock |
| Explicit duplicate `position` | 409 `CONTENT_CONFLICT` |
| `POST` without `external_id` | creates, 201 |
| `POST` with an existing `external_id` | updates that entity, 200 |
| `POST` with an existing `external_id` racing another request | 409 `EXTERNAL_ID_CONFLICT` |
| `PATCH` that changes an established `external_id`, or clears it with `null` | 409 `EXTERNAL_ID_CONFLICT` (a blank string is 422 `VALIDATION_ERROR`) |
| `PATCH` of an unknown id | 404 `RESOURCE_NOT_FOUND` |
| `DELETE` | 204; repeated `DELETE` → 404 `RESOURCE_NOT_FOUND` |
| Payload validation | entire payload validated before any mutation; one transaction per request |

Read serializers never expose storage keys, provider credentials or internal
flags. `external_id` is returned on the seven top-level entities.

## Resources

Routes (all with trailing slash):

| Resource | Collection | Detail |
|---|---|---|
| subjects | `GET, POST /api/v1/content/subjects/` | `GET, PATCH, DELETE /api/v1/content/subjects/{id}/` |
| sections | `GET, POST /api/v1/content/sections/` | `GET, PATCH, DELETE /api/v1/content/sections/{id}/` |
| topics | `GET, POST /api/v1/content/topics/` | `GET, PATCH, DELETE /api/v1/content/topics/{id}/` |
| blocks | `GET, POST /api/v1/content/blocks/` | `GET, PATCH, DELETE /api/v1/content/blocks/{id}/` |
| flashcards | `GET, POST /api/v1/content/flashcards/` | `GET, PATCH, DELETE /api/v1/content/flashcards/{id}/` |
| quizzes | `GET, POST /api/v1/content/quizzes/` | `GET, PATCH, DELETE /api/v1/content/quizzes/{id}/` |
| sources | `GET, POST /api/v1/content/sources/` | `GET, PATCH, DELETE /api/v1/content/sources/{id}/` |

Collection `GET` returns every row including drafts, ordered by
`(position, id)`, paginated. Detail `GET` returns the full representation.

### Payloads

```json
// POST /content/subjects/
{"title": "Pharmacology", "description": "", "position": 1, "external_id": "pharm-1"}
```

```json
// POST /content/sections/
{"subject": 1, "title": "Antibiotics", "description": "", "position": 2}
```

```json
// POST /content/topics/
{"section": 1, "title": "Beta-lactams", "description": "",
 "position": 1, "status": "published", "access_level": "free",
 "external_id": "topic-bl"}
```

```json
// POST /content/blocks/
{"topic": 9, "block_type": "image", "position": 2, "status": "published",
 "is_demo_preview": false, "markdown_body": "", "media": 5,
 "caption": "Structure"}
```

Block rules reuse feature 002: markdown/callout require `markdown_body`,
image requires `media`; publish preconditions are re-checked server-side and
`published_at` is server-assigned. `block_type` is addressed by its `key`.

```json
// POST /content/flashcards/
{"topic": 9, "question": "Which ring is strained?", "answer": "Beta-lactam",
 "position": 1, "external_id": "card-1"}
```

```json
// POST /content/quizzes/
{
  "topic": 9,
  "title": "Beta-lactams basics",
  "description": "",
  "position": 1,
  "external_id": "quiz-1",
  "questions": [
    {"text": "Which are beta-lactams?", "position": 1,
     "answers": [
       {"text": "Penicillin", "is_correct": true, "position": 1},
       {"text": "Gentamicin", "is_correct": false, "position": 2},
       {"text": "Cephalexin", "is_correct": true, "position": 3}
     ]}
  ]
}
```

```json
// POST /content/sources/
{"title": "Guideline", "source_type": "guideline", "author": "", "year": 2024,
 "url": "https://example.org", "note": "",
 "topic_ids": [9], "block_ids": [], "flashcard_ids": [3], "question_ids": [11]}
```

### Quiz aggregate contract

- `questions` and `answers` are nested; there are no separate question/answer
  routes.
- Items carrying `id` are updated in place (row ID preserved) and must belong to
  the addressed quiz (else 422 `INVALID_RELATION`). Items without `id` are
  created.
- Omitted items are **never deleted**; there is no child-deletion path.
- A quiz must keep at least one question; each question must keep at least two
  answers and at least one correct answer. Violations are 409 `CONTENT_CONFLICT`
  for an existing aggregate and 422 `VALIDATION_ERROR` for a create payload that
  cannot satisfy them.
- Detail `GET` returns nested questions and answers with their IDs; collection
  `GET` returns quiz scalar fields only.
- `PATCH` without `questions` leaves the aggregate children untouched.

### Source relations

`topic_ids`, `block_ids`, `flashcard_ids`, `question_ids` are set semantics: the
provided list becomes the complete relation set for that field inside the write
transaction. Unknown ids are 422 `INVALID_RELATION`. Deleting a Source removes
links only and never deletes content.

## Throttling

| Scope | Routes | Rate |
|---|---|---|
| `integration_write` | every route in this document | `120/min` |

Throttled requests return 429 `THROTTLED`.

## Errors

| Condition | HTTP | Code |
|---|---:|---|
| missing/wrong/empty integration key | 401 | `INTEGRATION_KEY_INVALID` |
| authenticated user without editor/admin role | 403 | `PERMISSION_DENIED` |
| unknown id | 404 | `RESOURCE_NOT_FOUND` |
| duplicate position, quiz aggregate invariant, blocked parent | 409 | `CONTENT_CONFLICT` |
| publish precondition failure | 409 | `INVALID_CONTENT_STATE` |
| external_id conflict or identity mutation | 409 | `EXTERNAL_ID_CONFLICT` |
| unknown relation or nested id from another quiz | 422 | `INVALID_RELATION` |
| shape/field/blank/unknown-field failure | 422 | `VALIDATION_ERROR` |
| rate limit | 429 | `THROTTLED` |

## OpenAPI

Every route is annotated with drf-spectacular: permission, request/response
serializers and the error responses above. All fourteen paths must appear in
`/api/v1/schema/`.
