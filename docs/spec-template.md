# Feature specification: `<feature-name>`

> Статус: Draft | Ready for implementation | Superseded  
> Owning app: `<django-app>`  
> Risk: Low | Medium | High  
> Related architecture: `<links>`  
> Related decisions: `<links>`

## Goal

Какую пользовательскую или системную проблему решает feature и какой результат
считается достигнутым.

## Scope

Точный набор поведения, endpoints, сущностей, migrations и integrations,
которые входят в эту задачу.

## Out of scope

Явный список близких, но не входящих изменений. Сюда же вынести deferred/TBD,
которые нельзя закрывать в рамках этой feature.

## Actors

Таблица actors: anonymous, user, editor, admin, system/integration и их
разрешённые действия.

## User scenarios

Для каждого сценария:

1. preconditions;
2. request/user action;
3. expected response/state change;
4. failure/alternative path.

## Entities

Какие существующие или новые entities затрагиваются, кто ими владеет и почему
feature находится в выбранном Django app.

## Business rules

Нумерованные правила, которые нельзя выводить только из UI или текущего
implementation. Каждое правило должно быть проверяемым.

## Invariants

Database constraints, uniqueness, allowed states, ownership, idempotency и
условия, которые должны оставаться истинными при повторных/конкурентных запросах.

## Data model

Опиши только нужные поля и relations:

- field, type, nullability, default;
- cardinality and `on_delete`;
- indexes/constraints;
- migration and backfill/rollback considerations.

Не добавляй поля «на будущее», если они не нужны acceptance criteria.

## API

Для каждого endpoint зафиксируй:

- method and exact URL under `/api/v1/`;
- authentication/permission/access policy;
- request headers/body/query;
- success status and response JSON;
- pagination/filter/sort;
- idempotency expectations;
- side effects.

## Permissions

Матрица `anonymous/user/editor/admin`, ownership checks, object-level checks и
paywall/access checks. Frontend visibility не считается permission.

## Validation

Required/optional/null/empty/boundary values, normalization, cross-field rules,
serializer vs service vs database responsibility.

## Errors

Таблица `condition → HTTP status → stable code → response shape`. Не описывать
только happy path.

## Edge cases

Missing/deleted/empty resources, duplicate requests, stale tokens, invalid
relations, last item/first item, concurrent update, retry, partial external
failure и boundary limits.

## Transactions

Где начинается и заканчивается atomic business operation, какие writes должны
откатиться вместе, какие внешние side effects выполняются после commit.

## Concurrency

Race scenarios, unique constraints, locking/version checks, idempotency и
ожидаемый ответ при конфликте.

## Background jobs/events

Синхронный или async flow, trigger, payload, retry/timeout, deduplication,
failure handling и observability. Если jobs/events не нужны, напиши это явно.
Не добавляй Celery/event bus без accepted decision.

## Security

Secrets, PII, authentication, authorization, CSRF/CORS, rate limits, input
sanitization, data exposure, audit/logging и abuse cases.

## Risks, compatibility and rollout

Backward compatibility, affected clients, migration order, deploy prerequisites,
rollback/forward-fix plan, data backfill and whether the feature requires a
coordinated frontend/backend release.

## Acceptance criteria

Нумерованные observable criteria. Каждый criterion должен быть однозначно
проверяемым тестом или ручной проверкой.

## Test scenarios

Раздели tests на:

- model/constraint;
- service/use case;
- selector/query;
- API success;
- API permission/security;
- validation/errors;
- transaction/concurrency;
- integration/storage/worker, если входит в scope.

## Dependencies

Другие features, apps, migrations, external services, environment variables,
frontend contract и docs, которые должны существовать до начала реализации.

## Open questions

Только блокирующие вопросы. Для каждого укажи, почему без решения нельзя
реализовать contract, и кто/какой decision должен его закрыть. Если вопросов нет,
напиши `None`.
