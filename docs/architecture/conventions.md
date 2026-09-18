# Backend conventions

Эти правила едины для новых Django apps и feature implementations. Если
конкретная feature spec задаёт более узкий контракт, она обязана явно объяснить
отклонение.

## Naming and layout

- Python modules, functions, variables и app labels — `snake_case`.
- Classes, serializers, services и selectors — `PascalCase`.
- Constants — `UPPER_SNAKE_CASE`.
- Domain apps — короткие lowercase names из target architecture.
- Models называют бизнес-сущности, а не технические таблицы.
- Use case functions называют действием: `publish_topic`, `submit_quiz`.
- Query functions/selectors называют чтением: `get_topic_detail`,
  `list_user_progress`.
- Не создавать generic `utils.py`, `helpers.py` или `misc.py` без конкретного
  domain-agnostic ownership.

## API URLs and schemas

- Prefix: `/api/v1/`.
- Resource URLs — plural nouns, trailing slash: `/api/v1/topics/`.
- Action URLs используют понятное действие только если это не обычный CRUD:
  `/api/v1/auth/token/refresh/`.
- Nested URLs неглубокие; не повторять всю DB hierarchy в URL без use case.
- JSON field names — `snake_case` как backend convention.
- IDs — numeric BigInt IDs; slugs предназначены для user-facing content URLs.
- Request и response serializers разделяются, когда их semantics различаются.
- Не отдавать serializer-ом внутренние flags, secrets, audit data или raw model
  fields без явного API contract.
- OpenAPI/Swagger должен отражать фактически реализованный contract.

## Error contract

Рекомендованный backend baseline для domain/API errors — единый envelope:

```json
{
  "code": "TOPIC_NOT_FOUND",
  "detail": "Topic not found."
}
```

Для validation errors допускается:

```json
{
  "code": "VALIDATION_ERROR",
  "detail": "Request validation failed.",
  "fields": {
    "username": ["This field is required."]
  }
}
```

`code` — стабильный machine-readable контракт; `detail` — краткое объяснение,
не заменяющее code. Не отдавать traceback, SQL, secrets или внутренние пути.
Это target recommendation, не существующий runtime и не закрытие принятого
глобального API decision register. До утверждения error decision конкретная
feature spec обязана явно закрепить свой response contract; она не должна
молча расходиться с этим baseline.

Рабочее соответствие:

| HTTP | Использование |
|---|---|
| 400 | malformed/invalid request |
| 401 | missing/invalid/expired authentication |
| 403 | authenticated, но role/access запрещает действие |
| 404 | resource не существует или недоступен по выбранной policy |
| 409 | конфликт уникальности/состояния |
| 429 | throttling/rate limit |
| 5xx | unexpected server/integration failure; без внутренних деталей клиенту |

## Validation

1. Serializer валидирует shape, type, format и простые cross-field input rules.
2. Service валидирует business rules и orchestration.
3. Model/database constraints защищают invariant при race conditions.
4. View не является местом основной validation/business logic.
5. Empty, null, malformed, duplicate и boundary cases должны быть явно покрыты
   tests и feature spec.

Content Markdown/raw HTML policy не считается автоматически решённой; её задаёт
content spec.

## Transactions and concurrency

- Transaction boundary — service/use case, не случайный view.
- Read-only selector не открывает transaction без причины.
- Multi-write use case использует одну понятную atomic boundary.
- Unique constraints обязательны для ownership/state pairs.
- При конкурирующих updates применять `select_for_update` или retry только если
  конкретный invariant этого требует и это описано в spec.
- Внешние HTTP/storage calls по возможности не выполняются внутри DB lock.
- Idempotency нужна только для операций, где повтор запроса реально опасен; не
  добавлять общий idempotency framework заранее.

## Tests

- Test runner: pytest.
- Tests лежат рядом с owning app: `apps/<domain>/tests/`.
- Минимальный набор изменённой feature: model/constraint, service, selector,
  API/permissions и negative/boundary cases по необходимости.
- Auth, permissions, paywall, migrations и destructive operations требуют
  explicit negative tests.
- Не подменять весь ORM моками там, где нужно доказать SQL/constraint/transaction.
- Fixtures/factories должны быть локальными и не содержать реальные secrets.

## Logging and observability

- Логи технические, структурированные настолько, насколько позволяет текущий
  setup.
- Включать event name, request/correlation id и безопасные entity ids.
- Auth/import/integration failures логировать с достаточным контекстом.
- Не логировать password, JWT, refresh cookie, Telegram secrets и raw sensitive
  payloads.
- Product event analytics и Sentry не добавлять без отдельного решения.

## Typing and tooling

- Python 3.12.
- Новый и изменённый код получает type annotations на public functions и
  service boundaries.
- Ruff отвечает за lint и format; команды проекта должны использовать `uv`.
- Конкретный type checker выбирается в foundation setup и не меняет domain
  boundaries.
- Не добавлять dependency только ради локального удобства, если стандартный
  Django/DRF механизм решает задачу.

## Migrations and data

- Каждое изменение model/schema сопровождается migration в том же изменении.
- Migrations коммитятся; уже применённую историю не переписывать.
- Destructive migration требует явного scope, backup/rollback considerations и
  отдельной проверки.
- Timestamps timezone-aware, storage in UTC.
- IDs используют BigAutoField/BigInt direction.
- Fixtures допустимы для deterministic test/demo data; secrets и production
  dumps запрещены.
- Для content и явно согласованных user-owned learning данных MVP использует
  physical deletion. Для User, RefreshSession, Subscription, Media и других
  доменов deletion/retention определяется entity-specific spec; общий soft/hard
  delete policy не выводится автоматически.

## Architecture guardrails

- Models не запускают core business logic через signals.
- API apps не превращаются в единый глобальный слой.
- Repository, UnitOfWork, EventBus, CommandBus и подобные abstraction layers не
  добавляются «на будущее».
- Redis пока cache; Celery/Kafka/RabbitMQ и новые integrations требуют decision.
- Optional content нельзя сделать required ради удобства текущего fixture.
- Если code/spec/ADR противоречат друг другу, остановиться и зафиксировать
  конфликт; не исправлять архитектуру молча.
