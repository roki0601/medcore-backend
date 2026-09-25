# Project memory

## Backend foundation

- Python 3.12 and `uv` are the project runtime and dependency-management baseline.
- Django settings are split into `base`, `local` and `production` modules.
- The custom `users.User` model is the configured `AUTH_USER_MODEL`; the first
  migration is already committed.
- Initial app boundaries are `common`, `users`, `content`, `learning`,
  `subscriptions` and `media`.
- The first slice intentionally does not implement JWT, Telegram auth, refresh
  sessions or domain content models.

## Runtime

- Local development uses PostgreSQL and Redis already running on the host.
- The server Compose stack contains Gunicorn web, PostgreSQL 16 and Redis 7.
- Redis is configured as Django cache only.
- Compose migrations are explicit through the one-shot `migrate` service and
  `make compose-migrate`; web startup does not run migrations implicitly.

## Quality gates

- Ruff is the formatter and linter; generated Django migrations are excluded.
- Pre-commit runs Ruff checks and formatting through the project `uv` environment.
- GitHub Actions runs formatting, lint, Django checks, migration checks and tests
  against PostgreSQL 16 and Redis 7 services.
- Project-local OMP uses behavior-focused test budgets, dependency-aware worker
  zones (up to four disjoint DeepSeek workers), one project-wide validation pass,
  and `high` thinking for DeepSeek roles. The wrapper disables session-title
  generation because an unavailable local title model previously added about
  96 seconds per manager/worker session before timing out; no local Qwen/Ufanet
  provider is registered anymore.
- OMP Telegram notifications use one final manager report per session with
  MarkdownV2 formatting. Successful child results stay silent; only actionable
  blockers are forwarded, and an unconfirmed session is reported as a warning
  rather than a fake successful completion.
- Backend OMP scope excludes `medcore-frontend`, which is owned by another
  model: do not inspect, synchronize, test, or modify it. Feature preflight
  covers only `medcore-docs` and `medcore-backend`.

## Source of truth

Product and architecture decisions are maintained in the neighboring
`medcore-docs` repository. Accepted decisions there take precedence over
implementation defaults.

## Current agreed MVP contract

- Registration/login uses verified Telegram Login Widget only.
- `users.User` stores `telegram_id` directly as the unique auth identity and
  stores a mutable unique application `username`; no separate Telegram identity
  table is planned.
- Auth uses Bearer access JWT plus non-rotating refresh JWT in an HttpOnly
  cookie with server-side revocation.
- Content follows `Subject -> Section -> Topic`; Topic access is
  `demo/free/paid`, and demo markers may exist on child content.
- Theory uses ordered Markdown/image/callout blocks. Flashcards and quizzes are
  separate Topic-owned entities; cards use a simple review scheduler and quizzes
  support multiple correct answers, partial scoring, retries and resumable
  attempts.
- External content is written synchronously through normal REST CRUD endpoints
  using a separate integration key. There is no import job or Celery worker for
  this flow.
- Media is stored outside PostgreSQL and private/paid files are exposed through
  short-lived signed URLs after backend access checks.
- Subscriptions core (BE-005) decisions D1–D8 are owner-approved and recorded in ADR 0009:
  - Stored statuses: `ACTIVE` and `CANCELLED`; expiry derived dynamically from timestamps (`starts_at <= now < expires_at`).
  - Entitlement grants access to all `paid` topics via `apps.subscriptions.policy.has_paid_content_entitlement(user)`.
  - Multiple overlapping subscriptions allowed; `get_active_subscription()` deterministically selects latest `expires_at`, tie-breaking on newest `id`.
  - No trial in BE-005 (architecture permits trial later without access model changes).
  - Cancellation is cancel-at-period-end (entitlement maintained until `expires_at`).
  - `Subscription.user` uses `CASCADE` on delete.
  - Endpoints: public `GET /api/v1/subscriptions/plans/` and authenticated `GET /api/v1/subscriptions/current/`.
  - Manual management via Django Admin.
- Payment provider integration (BE-006: Robokassa MVP):
  - Provider: Robokassa for one-time manual Plan purchase (no recurring/autopay, no stored card credentials, no background workers).
  - Fiscalization: Робочеки СМЗ (self-employed + "Мой налог"). Checkout GET redirect includes compliant `Receipt` parameter (`items` with name "Доступ к образовательной платформе Medcore — {duration} дней", quantity 1, sum from Decimal `Payment.amount`, `payment_method="full_payment"`, `payment_object="service"`, `tax="none"`). Serialized deterministically as compact UTF-8 JSON without float rounding; in GET-flow `receipt_encoded` is passed directly into URL parameters so that after server-side GET query decoding Robokassa receives the exact percent-encoded string used in `calculate_payment_signature` (`MerchantLogin:OutSum:InvId:Receipt:Password_1`), preventing Robokassa error 29. Buyer email is passed in initialization URL if available.
  - Model: `Payment` with fields `id` (InvId), `user`, `plan`, `subscription`, `amount` (immutable snapshot of plan price), `status` (pending/succeeded/failed), `provider`, `paid_at`.
  - Signatures: Password #1 for checkout URL; Password #2 for ResultURL callback. Constant-time comparison `hmac.compare_digest`.
  - Concurrency & Idempotency: `process_robokassa_result` runs in `transaction.atomic()` with `select_for_update()`; duplicate callbacks return `OK{InvId}` safely without creating extra subscriptions.
  - Endpoints:
    - `POST /api/v1/subscriptions/payments/` (`IsAuthenticated`, initiates payment, returns `payment_id`, `payment_url`);
    - `POST` / `GET` `/api/v1/subscriptions/payments/robokassa/result/` (`AllowAny`, validates signature, activates subscription, returns plaintext `OK{InvId}`);
    - `GET` / `POST` `/api/v1/subscriptions/payments/robokassa/success/` and `fail/` (buyer landing redirects/status).
- Progress and dashboard aggregate API (BE-007):
  - Endpoint: `GET /api/v1/dashboard/` (`IsAuthenticated`, throttle scope `learning_read`, unpaginated).
  - Scope: Only returns topics where user has active learning activity (theory progress, flashcard reviews, or quiz attempts).
  - Access Control: Re-evaluates topic access policy; inaccessible paid topics and their learning metrics do not leak if entitlement expires.
  - Performance: Zero N+1 query patterns; bounded O(1) query count using set-based annotations and filtered aggregates.
  - Metrics: Summary counters (`started_topics_count`, `completed_theory_topics_count`, `flashcards_due_count`, `quizzes_attempted_count`); per-topic canonical theory status/percent, due flashcards count, quiz attempted and best score (from submitted attempts only), sorted by `last_activity_at DESC`.
- Profile and study preferences (BE-008):
  - Model: `apps.users.models.UserProfile` (`OneToOneField` to `User`, `CASCADE`).
  - Fields: `university` (free text), `course` (1..6 or null), `semester_goal` (short text), `daily_study_minutes` (1..1440 or null), `selected_subjects` (M2M to `content.Subject`).
  - Endpoints: `GET /api/v1/profile/` and `PATCH /api/v1/profile/` (`IsAuthenticated`, throttle `account_mutation` for PATCH).
  - Semantics: Strictly private to own user; GET returns canonical empty profile or creates it safely; PATCH partially updates allowed profile fields while rejecting forbidden/auth fields (`telegram_id`, `username`, `role`); `selected_subject_ids` replaces full set; unknown IDs rejected with 400; independent of access control (does not alter topic demo/free/paid evaluation).
- Medcore JSON Admin Import:
  - Admin tool for importing topic documents generated by `medcore-content`.
  - Accessible via Django Admin Topics changelist button "Import Medcore JSON" at `/admin/content/topic/import-json/`.
  - Access restricted via `ContentPermissionMixin` (active staff with editor/admin role or superuser).
  - Form supports optional `Topic position`: if empty, appends to the end; if specified, `services.upsert_topic` and `_assign_position` (`shift=True`) automatically shift existing topics at or after that position down without unique constraint conflict.
  - Schema: Pydantic v2 schemas in `apps.content.import_schemas` enforcing `schema_version=1`, supported block types (`markdown`, `callout`), and quiz aggregate invariants (>= 2 answers per question, exactly 1 correct answer, unique answer texts).
  - Service: `apps.content.import_services.import_study_document` wraps all mutations in `transaction.atomic()`.
  - Identification: Deterministic external_id based on `medcore-content:topic:<section_identity>:<latin_base(topic_title)>` (where `section_identity` is `section.external_id` if present, else `section.pk`) isolates topics with identical titles across different sections and avoids duplicate topics on re-import.
  - Synchronization: Updates existing Topic, ContentBlock, Flashcard, and Quiz entities in place; safely removes stale/extra imported items without touching manually created items.
  - Positional matching limitation: Child entities are matched and updated by ordinal position (1..N). This preserves PKs only for elements remaining at the same position. Insertions or reordering can semantically rebind an existing PK to new content at that position; full cross-order entity preservation is deferred until medcore-content supplies persistent per-item external IDs.

## Current activity

- BE-001 through BE-008 are merged on `main`; BE-007 shipped in PR #15 and
  BE-008 in PR #16.
- `MVP_BACKEND_HARDENING` is in progress on
  `hardening/mvp-production-readiness`; it may harden accepted behavior but must
  not add product features or close unresolved product decisions.
- Medcore JSON Admin Import implemented and tested.
- BE-009 content bulk import and BE-010 slug URLs remain blocked/deferred.
- Local debug login endpoint `POST /api/v1/auth/dev/` (`DevLoginView`) added for frontend dev personas (`demo` and `premium`). Controlled via `DEV_AUTH_ENABLED` and `DEBUG`; returns 404 with `RESOURCE_NOT_FOUND` in production.

