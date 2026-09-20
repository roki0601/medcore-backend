# Open questions

Здесь остаются только вопросы, которые реально не закрыты принятыми ADR,
смёрженными feature specs или текущим runtime contract.

Telegram Login Widget verification, non-rotating revocable refresh sessions,
единый API error envelope, Topic `demo/free/paid`, synchronous Content API,
basic media URL flow, flashcard scheduling и quiz-attempt lifecycle больше не
являются open questions: они реализованы и покрыты соответствующими specs/tests.

## 1. Paywall and subscriptions

Базовая content access model уже принята и реализована:

- основной boundary — Topic;
- `access_level = demo | free | paid`;
- `demo` доступен anonymous;
- `free` требует authentication;
- `paid` требует authentication + entitlement;
- child elements внутри free/paid могут быть explicit demo preview;
- editor/admin role не является paid-access bypass;
- content и learning получают entitlement только через
  `apps.subscriptions.policy`.

Остаётся определить отдельной subscriptions spec:

- Plan/Tariff model и mapping plan → entitlement;
- Subscription status machine;
- overlap/renewal rules;
- trial eligibility и expiration;
- starts/expires/cancel semantics;
- retention и account-deletion behavior;
- как entitlement меняется при cancellation/expiry;
- payment provider boundary;
- webhook idempotency/authenticity и связь payment events с Subscription.

Конкретный payment provider всё ещё TBD. Его выбор не должен протекать в
`content` или `learning`.

## 2. Topic completion owner decisions

Backend 003 уже фиксирует `not_started / learning / learned`, manual completion
и theory-percent semantics.

Открыты два owner-level решения:

1. Какой threshold разрешает score-based automatic topic completion. Глобальный
   pass percentage нельзя придумывать молча.
2. Должен ли submitted quiz attempt продолжать раскрывать
   `correct_answer_ids`, если retakes остаются unlimited.

До первого решения backend возвращает score/results, но не делает
score-based auto-completion.

## 3. Profile and study preferences

Prototype показывает university, course, semester goal, daily load и selected
subjects. Эти данные не входят в текущие реализованные backend feature slices.

Нужно решить:

- входят ли они в MVP;
- какие поля действительно сохраняются;
- кто owns profile/preferences;
- нужна ли отдельная сущность «мои предметы»;
- privacy/update semantics.

## 4. Slugs and public URL stability

ADR 0008 оставляет slug вспомогательным URL-представлением, но текущий public
API использует numeric IDs.

Для будущих slug-based public URLs нужно определить:

- uniqueness scope;
- collision handling;
- allowed/manual override rules;
- нужны ли redirect/history после изменения slug.

Это не блокирует текущий numeric-ID API.

## 5. Content workflow extensions

Базовые content entities, published reads, manual published creation,
external-id upsert и synchronous Content API уже реализованы.

Для будущего расширения остаётся решить только то, чего текущий contract не
требует:

- дополнительные status transitions/workflow;
- preview unpublished content;
- отдельные bulk publish/import operations;
- removal semantics для массовой синхронизации внешнего набора.

Не добавлять ImportJob или очередь только ради этих будущих возможностей.

## 6. Production object storage

Media storage abstraction и S3-compatible adapter уже реализованы. Остаётся
deployment decision:

- конкретный S3-compatible provider;
- bucket/lifecycle/backups;
- production credentials/rotation;
- reverse-proxy/access-log configuration.

Protected bucket должен оставаться private. Capability URL paths
`/api/v1/media/upload/` и `/api/v1/media/file/` не должны попадать в access
logs.

## 7. Background jobs

Подтверждённого MVP use case, который требует Celery/worker, сейчас нет.
Synchronous services остаются default, Redis — cache.

Если появится конкретная долгая/асинхронная операция, отдельно определить:

- зачем она не может быть synchronous;
- retry/idempotency;
- queue ownership;
- operational/deployment cost.

До такого решения Celery/Kafka/RabbitMQ не добавляются.

## 8. Future identity extensions

Текущий MVP — Telegram-only и уже реализован.

Password/email auth, password reset, account linking и Telegram unlink являются
future scope, а не блокерами текущего MVP. Если они вернутся в roadmap, для них
нужен отдельный identity contract; не выводить их из legacy prototype.
