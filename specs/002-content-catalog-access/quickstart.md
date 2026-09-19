# Quickstart: Content catalog and Topic access

**Feature**: `002-content-catalog-access`  
**Prerequisites**: PostgreSQL and Redis reachable with the project `.env`;
`uv` installed; migrations applied.

## Setup

```bash
cd /home/roki/dev/medcore/medcore-backend
uv run python manage.py migrate
uv run python manage.py runserver 8000
```

Seed deterministic data through the content services (no secrets involved):

```bash
uv run python manage.py shell -c "
from apps.content.services import save_content_block, save_section, save_subject, save_topic
from apps.media.models import MediaFile

s = save_subject(title='Pharmacology')
sec = save_section(s, title='Antibiotics')
demo = save_topic(sec, title='Beta-lactams', status='published', access_level='demo')
free = save_topic(sec, title='Macrolides', status='published', access_level='free')
paid = save_topic(sec, title='Glycopeptides', status='published', access_level='paid')
draft = save_topic(sec, title='Hidden', status='draft', access_level='free')
save_content_block(demo, block_type_key='markdown', markdown_body='# Theory', status='published')
save_content_block(free, block_type_key='markdown', markdown_body='# Free', status='published')
save_content_block(free, block_type_key='callout', markdown_body='Preview', status='published', is_demo_preview=True)
m = MediaFile.objects.create(storage_key='k/1.png', mime_type='image/png', size_bytes=10)
save_content_block(paid, block_type_key='image', media=m, caption='Structure', status='published')
"
```

## Smoke sequence

1. `GET /api/v1/subjects/` → 200, paginated, contains `Pharmacology`.
2. `GET /api/v1/subjects/{s.id}/` → 200; missing id → 404 `RESOURCE_NOT_FOUND`.
3. `GET /api/v1/sections/{sec.id}/` → 200 with `subject` id.
4. `GET /api/v1/topics/` → 200 and contains only the three published topics
   (`Hidden` absent).
5. `GET /api/v1/topics/{demo.id}/` → 200 with `access_level: "demo"` and
   `has_demo_preview: false`.
6. `GET /api/v1/topics/{demo.id}/content/` anonymous → 200 with all published
   blocks and no `storage_key`.
7. `GET /api/v1/topics/{free.id}/content/` anonymous → 200 with exactly the
   published demo-preview block.
8. `GET /api/v1/topics/{paid.id}/content/` anonymous → 401
   `AUTHENTICATION_REQUIRED` (no preview block).
9. `GET /api/v1/topics/{paid.id}/content/` with a Bearer access token from a
   Telegram login → 403 `TOPIC_ENTITLEMENT_REQUIRED`.
10. `GET /api/v1/topics/{draft.id}/` and its content → 404.
11. `GET /api/v1/search/?q=mac` → 200 with the `Macrolides` topic result.
12. `GET /api/v1/search/?subject_id=999999` → 422 `INVALID_RELATION`.
13. `GET /api/v1/schema/` → contains the six content paths.

## Expected result

All checks pass; no response contains `storage_key`, a storage credential,
draft/generated/reviewed body, or a body the actor may not read. Repeated
catalog requests beyond the `catalog` throttle return 429 `THROTTLED`.

## Negative checks worth repeating manually

- Duplicate explicit `position` → 409 `CONTENT_CONFLICT`.
- Publishing an image block with `media=None` → 409 `INVALID_CONTENT_STATE`.
- `markdown_body` containing `<script>` → 422 `VALIDATION_ERROR`.
- Deleting a Topic removes only its own blocks; sibling topics/sections/subjects
  remain.