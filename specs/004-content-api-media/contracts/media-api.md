# API contract: Media metadata, upload and protected URLs

**Feature**: `004-content-api-media`
**Base**: `/api/v1/`
**Auth**: mixed per route (see the table below). Errors use the
`{code, detail, fields}` envelope.

## Routes

| Route | Permission | Purpose |
|---|---|---|
| `POST /api/v1/media/` | integration key or editor/admin JWT | create metadata (no binary) |
| `GET /api/v1/media/{id}/` | integration key or editor/admin JWT | read metadata |
| `DELETE /api/v1/media/{id}/` | integration key or editor/admin JWT | delete metadata and object |
| `GET /api/v1/media/{id}/upload-url/` | integration key or editor/admin JWT | issue the upload contract |
| `GET /api/v1/media/{id}/access-url/` | `AllowAny` (decision per visibility) | issue a short-lived read URL |
| `PUT /api/v1/media/upload/{token}/` | capability token only | controlled upload of the local backend |
| `GET /api/v1/media/file/{token}/` | capability token only | capability download of the local backend |

`storage_key` is never serialized. The integration principal is rejected on
`access-url` with 403 `INTEGRATION_SCOPE_FORBIDDEN` (metadata only).

## POST /api/v1/media/

```json
{"original_name": "structure.png", "mime_type": "image/png",
 "size_bytes": 20480, "checksum": "", "visibility": "protected"}
```

201 response:

```json
{"id": 5, "original_name": "structure.png", "mime_type": "image/png",
 "size_bytes": 20480, "checksum": "", "visibility": "protected",
 "created_at": "2026-09-19T08:00:00+05:00", "updated_at": "2026-09-19T08:00:00+05:00"}
```

Validation: `mime_type` must be in `MEDIA_ALLOWED_MIME_TYPES`; `size_bytes` must
be positive and at most `MEDIA_MAX_UPLOAD_BYTES`; unknown fields are rejected;
`storage_key` is generated server-side. Violations are 422 `MEDIA_INVALID` or 422
`VALIDATION_ERROR` for shape/unknown-field failures.

## GET /api/v1/media/{id}/upload-url/

200 response:

```json
{"upload_url": "http://localhost:8000/api/v1/media/upload/<token>/",
 "method": "PUT", "expires_at": "2026-09-19T08:10:00+05:00"}
```

The URL is provider-neutral: the local backend returns the controlled upload
endpoint, an S3-compatible backend returns a presigned `PUT` URL. The TTL is
`MEDIA_UPLOAD_URL_TTL` (600 s).

## PUT /api/v1/media/upload/{token}/

No user or integration authentication: the capability token is the credential.
It is bound to the `upload` operation, the media id, the `PUT` method and its
expiry, never contains the `storage_key`, and is never logged.

- Valid token + body → the object is written and verified against the declared
  `size_bytes` (and `checksum` when supplied). 204 on success.
- Expired or malformed token → 401 `AUTHENTICATION_REQUIRED`.
- Body size or checksum mismatch → 422 `MEDIA_INVALID`; nothing is stored.
- Backend without a controlled upload contract (`s3`) → 404
  `RESOURCE_NOT_FOUND`.

## GET /api/v1/media/{id}/access-url/

Decision order: resolve the media row (404 `RESOURCE_NOT_FOUND`), decide access,
then verify the object, then sign. Authorization always precedes any storage
call, so the endpoint is not an object-existence oracle.

| visibility | actor | result |
|---|---|---|
| `public` | anonymous or authenticated | 200 |
| `protected` | anonymous, no readable published reference | 401 `AUTHENTICATION_REQUIRED` |
| `protected` | anonymous, readable published demo/preview reference | 200 |
| `protected` | authenticated with Topic access to a published reference | 200 |
| `protected` | authenticated without access | 403 `MEDIA_ACCESS_DENIED` |
| any | integration principal | 403 `INTEGRATION_SCOPE_FORBIDDEN` |
| any | object missing or metadata mismatch | 422 `MEDIA_INVALID` |

"Readable published reference" means a published `ContentBlock` with this media
in a published Topic, evaluated with the feature 002 access composition
(`demo` full, `free` authenticated full, `paid` with entitlement, anonymous
preview only for published `is_demo_preview` blocks).

200 response:

```json
{"access_url": "http://localhost:8000/api/v1/media/file/<token>/",
 "method": "GET", "expires_at": "2026-09-19T08:10:00+05:00"}
```

TTL is `MEDIA_ACCESS_URL_TTL` (600 s). Expired URLs are not refreshed; the client
requests a new one and the access decision is re-evaluated.

## DELETE /api/v1/media/{id}/

- 204 after deleting the row and scheduling storage cleanup in
  `transaction.on_commit` (a provider failure is logged, never rolled back).
- 409 `CONTENT_CONFLICT` while a published content block references the file; the
  repair path is detaching the reference first — a published image block cannot
  stay published without media, so the client clears both in one request:
  `PATCH /api/v1/content/blocks/{id}/ {"status": "draft", "media": null}`.
- Unpublished references detach through `SET_NULL` when the row is deleted.
- Repeated `DELETE` → 404 `RESOURCE_NOT_FOUND`.

## Errors

| Condition | HTTP | Code |
|---|---:|---|
| expired/invalid capability token | 401 | `AUTHENTICATION_REQUIRED` |
| anonymous protected media without a readable reference | 401 | `AUTHENTICATION_REQUIRED` |
| integration principal on `access-url` | 403 | `INTEGRATION_SCOPE_FORBIDDEN` |
| protected media without access | 403 | `MEDIA_ACCESS_DENIED` |
| unsupported MIME, too large, failed verification, missing object | 422 | `MEDIA_INVALID` |
| published reference blocks deletion | 409 | `CONTENT_CONFLICT` |
| unknown media id | 404 | `RESOURCE_NOT_FOUND` |
| controlled upload on a backend without it | 404 | `RESOURCE_NOT_FOUND` |
| rate limit | 429 | `THROTTLED` |

## Throttling

| Scope | Routes | Rate |
|---|---|---|
| `media_upload` | `POST /media/`, `GET /media/{id}/upload-url/`, `PUT /media/upload/{token}/` | `30/min` |
| `media_metadata` | `GET /media/{id}/`, `DELETE /media/{id}/` | `60/min` |
| `media_access` | `GET /media/{id}/access-url/`, `GET /media/file/{token}/` | `60/min` |

## Storage adapter contract

`apps/media/storage.py` exposes `StorageAdapter` with
`create_upload_url(*, media, base_url)`, `create_access_url(*, media, base_url)`,
`verify_object(storage_key)`, `delete_object(storage_key)` and a
`supports_controlled_upload` capability.

- `LocalStorageAdapter` (`MEDIA_STORAGE_BACKEND=local`, default): objects under
  `MEDIA_STORAGE_ROOT`, capability URLs to the two controlled endpoints, sidecar
  `.meta` file recording the verified content type. A Django system check fails
  when this backend is selected with `DEBUG=False`.
- `S3StorageAdapter` (`MEDIA_STORAGE_BACKEND=s3`): S3-compatible endpoint,
  bucket, region, credentials and addressing style from the environment,
  presigned upload/access URLs, `head_object` verification. Its SDK (`boto3`) is
  an optional dependency group and its absence is a configuration error.

`apps/media` never imports `apps.content`: the access decision and the deletion
guard are content-owned functions resolved through
`MEDIA_ACCESS_POLICY_PROVIDER` and `MEDIA_DELETE_GUARD_PROVIDER`. A missing or
unresolvable provider fails closed (protected media denied, deletion refused).

The capability token of the two controlled endpoints travels in the URL path, so
the deployment must exclude the `/api/v1/media/upload/` and
`/api/v1/media/file/` prefixes from reverse-proxy and application access logs;
the TTL stays short (600 s) and the token is never written by application code.
An S3-compatible presigned URL necessarily contains the object key, so the
bucket must stay private (recorded in the spec's security section).

## OpenAPI

All seven paths are annotated with drf-spectacular: permissions, parameters,
response serializers and the error responses above.
