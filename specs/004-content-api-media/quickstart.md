# Quickstart: Synchronous content API and protected media

**Feature**: `004-content-api-media`
**Prerequisites**: PostgreSQL and Redis reachable with the project `.env`; `uv`
installed; migrations applied; `MEDCORE_CONTENT_API_KEY` set to a local test
value and `MEDIA_STORAGE_BACKEND=local`.

## Setup

```bash
cd /home/roki/dev/medcore/medcore-backend
uv run python manage.py migrate
uv run python manage.py runserver 8000
```

Seed one subject/section/topic through the content services (no secrets):

```bash
uv run python manage.py shell -c "
from apps.content.services import save_section, save_subject, save_topic

s = save_subject(title='Pharmacology')
sec = save_section(s, title='Antibiotics')
save_topic(sec, title='Beta-lactams', status='published', access_level='demo')
save_topic(sec, title='Macrolides', status='published', access_level='free')
"
```

## Smoke sequence

Integration key (`K`) is `MEDCORE_CONTENT_API_KEY`; user token (`T`) is a Bearer
access token from the Telegram login flow.

1. `POST /api/v1/content/subjects/` with `X-MedCore-Integration-Key: K` and
   `{"title": "Anatomy", "external_id": "anat-1"}` → 201; repeat the same request
   → 200 with the same `id`.
2. Same POST with a wrong key → 401 `INTEGRATION_KEY_INVALID`; with no key and no
   JWT → 401 `AUTHENTICATION_REQUIRED`.
3. Same POST with a valid user JWT whose role is `user` → 403 `PERMISSION_DENIED`;
   with an editor JWT → 201.
4. `POST /api/v1/content/sections/` with `{"subject": 999999, ...}` → 422
   `INVALID_RELATION`.
5. `POST /api/v1/content/quizzes/` with a nested question carrying two answers
   and one correct answer → 201; `PATCH` the same quiz with the same question
   `id` and new text → 200 and the question `id` is unchanged.
6. `PATCH` that quiz with one answer only → 409 `CONTENT_CONFLICT`; `POST` a quiz
   without `questions` → 422 `VALIDATION_ERROR`.
7. `POST /api/v1/media/` with `image/png` and 20480 bytes → 201 and no
   `storage_key` in the response; with `text/html` → 422 `MEDIA_INVALID`.
8. `GET /api/v1/media/{id}/upload-url/` → 200 with `upload_url` and `expires_at`;
   `PUT` exactly the declared bytes to it → 204; `PUT` fewer bytes → 422
   `MEDIA_INVALID`.
9. `POST /api/v1/content/blocks/` with `block_type: "image"`, the media id and
   `status: "published"` in a demo topic → 201.
10. `GET /api/v1/media/{id}/access-url/` anonymous → 200 (public media) or, for
    `protected` media in a demo topic, 200; for `protected` media in a `free`
    topic anonymous → 401 `AUTHENTICATION_REQUIRED`; with a `user` JWT → 200;
    with the integration key → 403 `INTEGRATION_SCOPE_FORBIDDEN`.
11. `GET` the returned `access_url` → 200 with the uploaded bytes; wait past the
    TTL and reuse it → 401 `AUTHENTICATION_REQUIRED`.
12. `DELETE /api/v1/media/{id}/` while the published block references it → 409
    `CONTENT_CONFLICT`; after `PATCH` the block with
    `{"status": "draft", "media": null}` (an image block cannot stay published
    without media) → 204, and a repeated `DELETE` → 404 `RESOURCE_NOT_FOUND`.
13. `DELETE /api/v1/content/topics/{id}/` → 204; sibling topics, sections and
    subjects remain; the topic's blocks, flashcards and quizzes with their
    questions/answers are gone.
14. `GET /api/v1/schema/` contains all fourteen `/content/` paths and the seven
    `/media/` paths.
15. Repeated integration writes beyond `integration_write` → 429 `THROTTLED`.

## Expected result

All checks pass. No response contains `storage_key`, a provider credential, a
capability token, or a raw integration key. `manage.py check` fails when
`MEDIA_STORAGE_BACKEND=local` is combined with `DEBUG=False`.

## Negative checks worth repeating manually

- `POST /api/v1/content/subjects/` with an unknown top-level field → 422
  `VALIDATION_ERROR` naming that field.
- `PATCH /api/v1/content/subjects/{id}/` changing `external_id` → 409
  `EXTERNAL_ID_CONFLICT`.
- Duplicate explicit `position` → 409 `CONTENT_CONFLICT`.
- Publishing an image block without media → 409 `INVALID_CONTENT_STATE`.
- `markdown_body` containing `<script>` → 422 `VALIDATION_ERROR`.
