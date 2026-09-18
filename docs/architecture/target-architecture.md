# Target architecture

Статус: целевая backend-основа для MVP. Документ фиксирует placement и
границы кода; продуктовые `TBD` не закрываются здесь молча.

## Architectural style

MedCore — Django + Django REST Framework modular monolith с PostgreSQL и Redis.
Frontend и backend остаются отдельными репозиториями и общаются только через
versioned REST API.

```text
Next.js frontend
        │ HTTPS / JSON / Bearer access JWT
        ▼
Django + DRF modular monolith
  ┌──────────────┬──────────────┬──────────────┐
  │ users        │ content      │ learning     │
  │ subscriptions│ media        │ common       │
  └──────────────┴──────────────┴──────────────┘
        │                 │                 │
        ▼                 ▼                 ▼
   PostgreSQL          Redis cache      Object storage
```

AI-инструменты генерации контента не участвуют в пользовательском runtime.
Фоновые очереди, event bus и microservices не добавляются до отдельного
решения.

## Repository boundary

Целевая структура — ориентир, а не требование создавать пустые packages:

```text
medcore-backend/
├── manage.py
├── pyproject.toml
├── uv.lock
├── Dockerfile
├── .env.example
├── README.md
├── AGENTS.md
├── config/
│   ├── settings/
│   │   ├── base.py
│   │   ├── local.py
│   │   └── production.py
│   ├── urls.py
│   ├── api.py
│   ├── asgi.py
│   └── wsgi.py
├── apps/
│   ├── common/
│   ├── users/
│   ├── content/
│   ├── learning/
│   ├── subscriptions/
│   └── media/
└── tests/                         # только если нужен cross-domain слой
```

Большие apps могут стать packages с `models/`, `api/`, `services/`,
`selectors/`, `admin/`, `tests/`. Маленький app вправе использовать `models.py`,
`services.py` и `admin.py`. Структура определяется сложностью текущего домена,
а не симметрией.

## Django apps и ownership

| App | Owns | Не owns |
|---|---|---|
| `users` | User, credentials, Telegram identity, auth/account lifecycle, refresh revocation | content, learning, subscriptions, paywall |
| `content` | Subject, Section, Topic, ContentBlock/ContentBlockType, Flashcard, Quiz, QuizQuestion/Answer, Source, CMS/import flow | user progress, auth, subscription internals |
| `learning` | UserTopicProgress, FlashcardReview, QuizAttempt и use cases обучения | авторский content, user identity, tariffs |
| `subscriptions` | Plan/Tariff, Subscription, trial/status lifecycle и access/entitlement policy | User credentials, content authoring |
| `media` | Media/File metadata, object-storage adapter и file lifecycle | content semantics, user progress |
| `common` | только domain-agnostic primitives: time, API error base, request context и т.п. | бизнес-сущности и произвольные `utils.py` |

`content` остаётся единым domain app на MVP. `catalog`, `practice`, `import`
и `access` не создаются как отдельные Django apps без нового решения.

## Dependency direction

Разрешённое направление:

```text
users       media
  ▲           ▲
  │           │
content ─────┘
  ▲
  │
learning

subscriptions ───► users

Application/API access composition:
content.application ───► subscriptions.policy
learning.application ──► subscriptions.policy
```

Правила:

- `users` не импортирует `content`, `learning` или `subscriptions`;
- `media` не импортирует business domains;
- `content` может ссылаться на `users` для review/audit и на `media` для
  metadata/asset references;
- `learning` может зависеть от `users` и `content`;
- `subscriptions` зависит от `users` и owns access policy;
- `content` и `learning` application/API layers могут вызывать только публичную
  `subscriptions` policy interface для access decision; они не импортируют
  Subscription models. Обратные imports запрещены;
- content models/selectors не знают полей или статусов Subscription;
- никакого циклического импорта между domain apps.

Access composition выполняется только application service на стороне owning
domain: он получает resource capability из своего domain selector, вызывает
публичную `subscriptions.policy`, а затем передаёт selector-у только готовый
access context/allowed result. Selector не импортирует Subscription models или
policy напрямую; `subscriptions` не импортирует `content`/`learning`. Точный
granularity paywall остаётся вопросом продукта.

## Responsibilities by layer

### Models

Models описывают persistence, relations, database constraints и локальные
инварианты своей сущности. Они не запускают cross-domain use cases и не
содержат скрытый business flow через signals.

### API

Каждый domain app владеет своими `urls`, serializers/schemas, views и
permissions. Views/ViewSets делают только HTTP orchestration:

1. parse request;
2. вызвать serializer validation;
3. выполнить permission/access checks;
4. вызвать service или selector;
5. сериализовать результат и вернуть response.

Общее глобальное `api/` для всех domain endpoints не вводится. `config` только
подключает versioned app URLs и инфраструктурные endpoints.

### Services

Service — место write/use-case логики, если операция меняет состояние,
пересекает несколько моделей, имеет бизнес-правила или требует атомарности.
Примеры: `publish_topic`, `submit_quiz`, `complete_topic`, `logout_all`.
Тривиальный `.save()` не оборачивается в service без причины.

### Selectors

Selector — место сложного или повторно используемого read query с joins,
`prefetch_related`, annotations или access-aware filters. Простой одношаговый
`Model.objects.get()` не требует selector.

### Persistence/repositories

Отдельный repository/unit-of-work слой не вводится. Django ORM является
persistence abstraction. Новая абстракция допустима только при доказанной
текущей потребности и явной фиксации причины в feature spec/decision.

### Admin/CMS

`content` владеет Django Admin для авторского контента и import/publish
операций. Admin permissions не заменяют API permissions. Editor не получает
user/system administration.

## API boundary

- Все пользовательские REST URLs начинаются с `/api/v1/`.
- URL используют plural nouns и trailing slash по convention DRF.
- Внутренние relations используют numeric `BigAutoField` IDs.
- User-facing content URLs используют slugs; scope uniqueness и redirect policy
  должны быть определены feature spec до реализации.
- API — REST/JSON; OpenAPI/Swagger публикуется для фактически реализованных
  endpoints.
- Access JWT передаётся в `Authorization: Bearer <token>`.
- Refresh token хранится в защищённой `httpOnly` cookie и должен быть
  revocable.
- Не вводить глубокую nested URL-структуру без сценария, который этого требует.

## Access boundary

Нужно различать четыре проверки:

1. authentication — кто пользователь;
2. role permission — может ли его роль выполнить операцию;
3. product access policy — есть ли free/subscription/trial capability;
4. domain invariant — допустима ли операция по состоянию сущности.

`premium` не является ролью. Не помещать subscription checks в serializers или
content models; policy вызывается явно на application boundary.

## Transactions and side effects

- Одна атомарная business operation имеет одну понятную `transaction.atomic`
  boundary в service/use case.
- Database constraints являются второй линией защиты после service validation.
- Concurrent updates используют row locks/unique constraints только там, где
  это следует из конкретного инварианта.
- Django signals не используются для core business logic.
- Cache invalidation выполняется явно в сервисе рядом с изменением данных.
- Внешние вызовы не удерживаются внутри длинной DB-транзакции без причины.

## Background jobs and integrations

| Интеграция | Boundary | MVP policy |
|---|---|---|
| Telegram | `users` auth adapter/service | backend verifies Telegram identity; protocol details in auth spec |
| Object storage | `media` adapter | binary outside PostgreSQL; provider TBD |
| Content import | `content/importing` | normalized JSON; admin/manual or semi-automatic flow; exact upsert TBD |
| Payments | `subscriptions` future adapter | provider, scope and webhook boundary TBD; no integration until decision |
| AI/Notebook | outside user runtime | produces importable content only |
| Async workers | no app yet | Celery/Kafka/RabbitMQ require separate decision |

По умолчанию операции MVP выполняются синхронно через service. Нельзя
самостоятельно добавлять Celery, retry loop, event bus или scheduled job.

## Foundation constraints

- PostgreSQL — primary datastore; Redis — cache only until отдельное решение;
- timestamps timezone-aware, persist in UTC;
- migrations committed with model changes;
- secrets only through environment/secret manager, never source control;
- CORS and trusted origins limited to configured frontend domains;
- DRF throttling enabled for auth and other abuse-sensitive endpoints;
- technical logs must not contain passwords, tokens or raw sensitive payloads.

## How to extend the architecture

Новая функциональность сначала получает owning app из этой таблицы. Если она
пересекает несколько domains, owning app определяется use case, а не моделью,
которой принадлежит большинство полей. Новое Django app, новая cross-domain
dependency, новая infrastructure technology или изменение публичного API
требуют сначала обновить architecture/spec/decision, а не принимать решение в
коде.
