# Data model: Telegram auth and user account

## User (`users.User`)

Existing custom `AbstractUser`, preserved as the account owner.

| Field | Contract |
|---|---|
| `id` | Django `BigAutoField`; internal numeric identity. |
| `username` | Required application username; NFKC-normalized, trimmed, lower-cased; 3–30 characters; only Latin letters, digits, `.`, `_`, `-`; case-insensitively unique; mutable and not an auth identity. |
| `password` | Existing Django hash field remains; Telegram-only accounts receive an unusable password. Password login is out of scope. |
| `email` | Existing nullable optional field; not part of this API. |
| `telegram_id` | Nullable for legacy rows, unique `BigIntegerField`; required for new Telegram-created users and canonical account lookup. |
| `telegram_username` | Existing optional snapshot of the verified Telegram username; changing it never changes application `username`. |
| `role` | `user`, `editor`, `admin`; new Telegram users always receive `user`. |
| `is_active` | Existing boolean; inactive users cannot authenticate, refresh or use authenticated APIs. |
| `auth_version` | Existing positive integer; included in tokens and compared by authentication. |
| `created_at`, `updated_at` | Timezone-aware UTC timestamps. |

## RefreshSession (`users.RefreshSession`)

One User has many non-rotating refresh sessions.

| Field | Contract |
|---|---|
| `id` | Django `BigAutoField`. |
| `user` | Required FK to `users.User`, `on_delete=CASCADE`, owned by users. |
| `jti` | Required unique non-secret JWT identifier; raw refresh JWT is never stored. |
| `auth_version` | User auth-version snapshot used during refresh validation. |
| `expires_at` | Required UTC timestamp. |
| `revoked_at` | Nullable UTC timestamp; set by logout/logout-all/security operations. |
| `created_at` | UTC timestamp. |
| `last_used_at` | Nullable UTC timestamp updated while the row is locked and valid. |

Indexes cover `(user, revoked_at)` and `expires_at`. Refresh validation locks
this row before checking revocation/expiry and updating `last_used_at`.

## TelegramLoginReplay (`users.TelegramLoginReplay`)

Durable one-time consume record for the verified legacy widget payload.

| Field | Contract |
|---|---|
| `id` | Django `BigAutoField`. |
| `digest` | Required unique lowercase SHA-256 hex digest of the complete canonical verified data-check string. One-way; no raw payload. |
| `expires_at` | Required UTC timestamp derived from `auth_date + 86400 seconds`; indexed for future reviewed cleanup. |
| `created_at` | UTC timestamp. |

The record is inserted in the same transaction as User/RefreshSession creation.
A duplicate digest aborts authentication as an exact replay. Rows are retained
for MVP to avoid replay bypass through eviction/deletion; no queue or cleanup
worker is introduced.

## Cross-domain deletion contract

Learning feature 003 owns `UserTopicProgress`,
`UserTopicSectionProgress`, `FlashcardReview` and `QuizAttempt`. Each required
User FK must use database `ON DELETE CASCADE`. `users` does not import learning.
Account deletion revokes `RefreshSession` rows before deleting User; PostgreSQL
then removes those learning-owned rows when present.

## Invariants

- No duplicate `telegram_id` or case-insensitive application username.
- No replay digest can be consumed twice, including concurrent requests.
- No revoked/expired/auth-version-mismatched RefreshSession can refresh.
- No raw Telegram payload, bot token, refresh JWT or access JWT is persisted or
  logged.
- Account deletion is atomic with session revocation.
- Anonymous requests never create User or session state.
