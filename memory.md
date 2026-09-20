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
- Subscriptions and payment semantics remain explicitly unresolved (BE-005
  proposal is pending owner decisions D1–D8).
