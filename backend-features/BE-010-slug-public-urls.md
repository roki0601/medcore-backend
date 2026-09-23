# BE-010 — Slug-based public URLs

Status: IMPLEMENTED

Owner decision, 2026-09-23:

- public canonical URLs are `/{subject_slug}` and `/{subject_slug}/{topic_slug}`;
- section is not part of the URL;
- old numeric public URLs are not redirected;
- subject slug stays globally unique; topic slug stays globally unique, which is
  stricter than unique-within-subject and still satisfies that URL;
- a slug is generated once, in Latin kebab-case, and is not regenerated when the
  title changes;
- numeric API routes stay for admin, learning and existing clients;
- IndexNow and slug history are out of scope.

## Public reads

- `GET /api/v1/subjects/by-slug/{slug}/`
- `GET /api/v1/topics/by-slug/{subject_slug}/{topic_slug}/`
- `GET /api/v1/catalog/sitemap/`

Draft topics are not found. Numeric routes and content access rules are unchanged.
