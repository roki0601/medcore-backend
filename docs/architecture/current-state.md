# Current state

Статус среза: 2026-09-20 после merge backend features 001, 002, 004, 003 и
OpenAPI contract follow-up.

Этот документ описывает фактическое состояние `medcore-backend`, а не желаемый
результат. Целевая backend-архитектура находится в
[`target-architecture.md`](target-architecture.md).

## Краткий вывод

Backend больше не является foundation/skeleton-проектом. На текущем `main`
реализованы и смержены:

- Telegram-only authentication и account lifecycle;
- публичный content catalog и Topic-level access model `demo/free/paid`;
- synchronous content authoring API;
- provider-neutral media layer с local dev backend и S3-compatible production
  backend;
- server-backed learning state: topic progress, block completion, flashcard
  review и quiz attempts;
- OpenAPI contract, согласованный с runtime payloads/errors/auth.

Следующая крупная backend-граница — `subscriptions/paywall`. Для неё уже есть
public policy seam, но реального entitlement storage, Plan/Subscription
lifecycle и payment integration ещё нет.

## Что реально есть в backend-репозитории

| Область | Фактическое состояние |
|---|---|
| Django project | `manage.py`, `config/`, settings, ASGI/WSGI, versioned URLs |
| Django apps | `common`, `users`, `content`, `learning`, `subscriptions`, `media` |
| User/auth | custom User, unique `telegram_id`, mutable unique username, roles; Telegram Login Widget, access JWT, HttpOnly refresh session, revocation, logout/logout-all, self-delete |
| Content | Subject, Section, Topic, ContentBlock, Source, Flashcard, Quiz/Question/Answer; public catalog/read API and controlled authoring API |
| Access | Topic `demo/free/paid`, anonymous demo/preview, free-after-auth, paid-through `subscriptions.policy` |
| Learning | topic progress, block completion, flashcard reviews/scheduling, persisted/resumable quiz attempts and submit results |
| Subscriptions | app + `has_paid_content_entitlement(user)` policy seam; currently deny-by-default, no Plan/Subscription storage yet |
| Media | MediaFile metadata, upload/access URL flow, local dev storage, S3-compatible adapter, protected access policy |
| Integration | synchronous REST content API with separate integration key; no ImportJob/Celery |
| REST API | `/api/v1/`, common error envelope, pagination, scoped throttling and feature permissions |
| OpenAPI | drf-spectacular schema/docs; runtime contracts covered by follow-up tests |
| Database/cache | PostgreSQL + Redis cache |
| Dependencies | `pyproject.toml` + `uv.lock`, Python 3.12 |
| Tests/tooling | pytest/pytest-django, Ruff, pre-commit, GitHub Actions |
| Infrastructure | Dockerfile, Compose, environment configuration, Gunicorn; production object-storage provider still deployment TBD |

## Реализованные feature slices

### 001 — Telegram auth and account

Реализованы verified Telegram Login Widget payload, replay/freshness protection,
access JWT + server-revocable refresh sessions, CSRF-protected cookie
operations, current account read/update, logout, logout-all и account deletion.

Password/email registration/login не являются частью текущего MVP по ADR 0008.

### 002 — Content catalog and access

Реализованы hierarchy `Subject → Section → Topic`, published content blocks,
public-safe catalog/search и единый Topic access boundary:

- `demo` — доступен anonymous;
- `free` — полный доступ после authentication;
- `paid` — требует entitlement;
- free/paid могут отдавать explicit demo preview.

Реальный paid entitlement пока отсутствует: текущая
`apps.subscriptions.policy.has_paid_content_entitlement` честно возвращает
`False` до отдельной subscriptions feature.

### 004 — Content API and media

Реализован synchronous authoring API для content entities, external IDs/upsert,
integration-key authentication, media metadata/storage abstraction и
upload/access URL flow.

Local storage предназначен только для dev/test и запрещён system check вне
`DEBUG`. Production использует S3-compatible adapter после настройки
конкретного provider.

### 003 — Learning state

Реализованы:

- `not_started / learning / learned` topic state;
- completion опубликованных theory blocks и derived theory percent;
- flashcard `know/repeat` scheduling;
- review-due;
- persisted quiz attempts, resume, answer state и submit;
- frozen submitted results and best score derivation;
- permission/access re-checks for every learning operation.

Глобальный quiz pass threshold и score-based automatic topic completion
намеренно не реализованы до owner decision.

## Что ещё не реализовано

- Plan/Tariff/Subscription models и реальный entitlement source;
- subscription status machine, trial/expiry/cancellation/overlap semantics;
- payment provider и webhook boundary;
- score threshold для automatic topic completion;
- финальное решение, нужно ли раскрывать `correct_answer_ids` после submit при
  unlimited retakes;
- конкретный production object-storage provider;
- slug-based public user-facing URLs и redirect/history policy;
- отдельные bulk/import workflow сверх уже существующего synchronous REST API;
- background jobs/queue infrastructure — текущего подтверждённого MVP use case
  для них нет.

## Контекст из соседних репозиториев

`medcore-docs` остаётся источником принятых продуктовых решений. Важные
источники:

- `decisions/0004-mvp-decision-register.md`;
- `decisions/0005-decision-register-audit.md`;
- `decisions/0006-anonymous-demo-content.md`;
- `decisions/0007-content-access-model.md`;
- `decisions/0008-mvp-auth-content-and-integration-contract.md`;
- `product/mvp.md`;
- `ai/context.md`.

`medcore-frontend` содержит frozen prototype/styleguide как visual reference и
production Next.js implementation. Prototype-local auth/progress formulas не
являются backend contract.

## Что следует считать source of truth

1. Более новые явно принятые decisions/ADR в `medcore-docs`.
2. Backend-specific architecture в `docs/architecture/`.
3. Approved implementation-ready feature spec + recorded delegated decisions.
4. Existing code/tests как фактическая baseline-реализация; конфликт с более
   высоким source of truth должен быть эскалирован, а не принят молча.

## Итог для следующего этапа

Foundation, auth, content, media и learning повторно проектировать не нужно.
Следующий backend product slice — `subscriptions/paywall`: сначала
implementation-ready spec и owner decisions, затем plan/tasks и реализация.
Параллельно frontend может потреблять уже смерженные media/learning contracts.
