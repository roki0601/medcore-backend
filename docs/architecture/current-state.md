# Current state

Статус среза: 2026-09-18 после merge backend foundation.

Этот документ описывает фактическое состояние `medcore-backend`, а не желаемый
результат. Целевая backend-архитектура находится в
[`target-architecture.md`](target-architecture.md).

## Краткий вывод

Backend foundation уже реализован. Репозиторий больше не является пустым
skeleton: создан Django/DRF project, базовые domain apps, custom User,
PostgreSQL/Redis configuration, healthcheck, OpenAPI, Docker/Compose и quality
tooling.

При этом продуктовые feature domains ещё в основном не реализованы: content,
learning, subscriptions и media пока содержат только app skeleton, а полноценный
auth/JWT flow ещё должен быть реализован по feature specs.

## Что реально есть в backend-репозитории

| Область | Фактическое состояние |
|---|---|
| Django project | есть `manage.py`, `config/`, settings, ASGI/WSGI, URLs |
| Django apps | `common`, `users`, `content`, `learning`, `subscriptions`, `media` |
| User model | есть custom `users.User`: unique username, optional email/telegram identity, roles, timestamps |
| Content models | ещё не реализованы |
| Learning models | ещё не реализованы |
| Subscription models | ещё не реализованы |
| Media models | ещё не реализованы |
| REST API | foundation есть; `/api/v1/health/` реализован |
| Authentication | Django auth foundation есть; JWT/Telegram/password API flow ещё не реализован |
| OpenAPI | `drf-spectacular` подключён, docs доступны через `/api/v1/docs/` |
| Database | PostgreSQL configured |
| Cache | Redis configured as Django cache |
| Dependencies | `pyproject.toml` + `uv.lock`, Python 3.12 |
| Tests/tooling | pytest, pytest-django, Ruff, pre-commit configured |
| Infrastructure | Dockerfile, `compose.yaml`, `.env.example`, Makefile, GitHub automation |
| Documentation | `AGENTS.md`, architecture docs, spec template и example spec |

Backend foundation был смержен в `main` 2026-09-18. Поэтому новые агенты должны
считать существующий код и tooling реальной baseline-реализацией, а не
планируемой структурой.

## Уже реализованные foundation decisions

- Django + DRF modular monolith;
- Python 3.12 + `uv`;
- PostgreSQL как primary datastore;
- Redis как cache;
- domain apps: `users`, `content`, `learning`, `subscriptions`, `media`, `common`;
- custom User с `BigAutoField` direction, username, optional email/Telegram identity, role;
- `/api/v1/health/` как anonymous liveness endpoint;
- OpenAPI через drf-spectacular;
- CORS/CSRF configuration hooks;
- Docker/Compose и Gunicorn;
- pytest + Ruff + pre-commit.

Эти foundation choices уже представлены в коде. Менять их как будто это ещё
чистый design space нельзя без отдельного решения.

## Что ещё не реализовано

- JWT access/refresh и refresh revocation/blacklist;
- Telegram verification/login;
- password registration/login/reset/change;
- content domain models и API;
- learning/progress models и API;
- Plan/Subscription/paywall policy;
- Media/File storage integration;
- import/bulk publish workflow;
- throttling policy по конкретным endpoints;
- feature-specific permissions;
- основные product feature tests.

## Контекст из соседних репозиториев

`medcore-docs` остаётся источником принятых продуктовых решений. Важные
источники:

- `decisions/0004-mvp-decision-register.md` — исходный подробный реестр;
- `decisions/0005-decision-register-audit.md` — аудит и правила приоритета;
- `decisions/0006-anonymous-demo-content.md` — более новое решение о публичном
  demo-контенте до авторизации;
- `product/mvp.md`;
- `architecture/*`;
- `ai/context.md` и `AGENTS.md`.

`medcore-frontend` содержит статический prototype «Кафедра», styleguide и
frontend spec. Он является визуальным/поведенческим референсом, но localStorage,
demo IDs и локальная auth-имитация не являются backend contract.

## Актуальные продуктовые различия с frontend prototype

- demo auth во frontend использует email, тогда как backend baseline использует
  unique username и optional email;
- anonymous demo flow теперь является принятым продуктовым направлением, но его
  точная backend-модель должна быть определена content feature spec;
- frontend demo хранит progress в localStorage, тогда как настоящий progress
  принадлежит `learning` и после auth хранится на backend;
- frontend prototype может содержать временные формулы прогресса/пороги; они не
  становятся backend contract без отдельного решения.

## Что следует считать source of truth

1. Более новые явно принятые decisions/ADR в `medcore-docs`.
2. Backend-specific architecture в `docs/architecture/`.
3. Approved implementation-ready feature spec.
4. Existing code/tests как фактическая baseline-реализация; конфликт с более
   высоким source of truth должен быть эскалирован, а не принят молча.

## Итог для следующего этапа

Foundation повторно создавать не нужно. Следующий этап — reconciliation
оставшихся open questions и написание feature specs, после чего coding-agent
реализует auth/content/learning/subscriptions поверх уже существующего skeleton.
