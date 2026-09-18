# Open questions

Здесь только вопросы, которые влияют на продуктовый контракт или границы
архитектуры. Локальные имена функций, ORM-оптимизации и прочие implementation
details сюда не выносятся.

## 1. Telegram protocol and account linking

Нужно зафиксировать конкретный Telegram mechanism (Login Widget, Mini App
init-data или другой), проверяемые claims, timestamp/replay policy, создание
нового User, linking существующего password account и future unlink behavior.

Без этого нельзя написать безопасный implementation-ready Telegram spec.

## API permission baseline and error contract

Нужно принять, будет ли `IsAuthenticated` глобальным default с явным public
allowlist или permissions будут назначаться endpoint-by-endpoint. Отдельно нужно
утвердить точную нормализацию DRF validation errors и единый error envelope
(`code`, `detail`, field errors/status mapping). До решения feature specs должны
указывать эти контракты явно.

## Refresh rotation and reuse policy

Revocation/blacklist refresh tokens уже обязательны. Нужно отдельно решить,
использует ли общий auth слой rotation/reuse detection или допускает
non-rotating refresh tokens. Example spec содержит локальный non-rotating choice,
но не закрывает глобальный auth decision.

## Production cookie topology

Текущий план использует Vercel и Render, но production refresh cookie требует
поддерживаемую first-party topology: sibling custom domains под одним
registrable domain или same-origin backend proxy/BFF. Нужно выбрать topology,
credentialed CORS/trusted origins и browser support policy до production auth
rollout.

## 2. Password reset and account deletion

Password reset объявлен обязательным, но email optional, delivery channel и
identity verification не определены. Нужно выбрать reset channel/expiry/rate
limits. Для self-delete нужно подтвердить re-authentication/confirmation и
retention policy для удалённых данных.

## 3. Profile and study preferences

Prototype показывает university, course, semester goal, daily load и selected
subjects. Backend architecture пока фиксирует только User и learning/content
entities.

Нужно решить, входят ли эти поля и «мои предметы» в MVP backend, кто owns их и
сохраняются ли они как profile/preferences entities.

## 4. Subject/Section/Topic contract

Нужно утвердить полный MVP field set и relationships, включая:

- display/order semantics;
- section/topic status and visibility;
- topic summary/duration/latin title, если они обязательны;
- поведение пустых разделов и тем.

## 5. Slugs and URL stability

Нужно определить uniqueness scope slug (global или внутри parent), collision
handling, allowed characters, manual override validation и нужны ли redirect/
history после изменения опубликованного slug.

## 6. ContentBlock workflow

Нужно зафиксировать:

- список и lifecycle ContentBlockType;
- ordering mechanism;
- raw HTML policy для Markdown;
- кто может переводить status и какие переходы разрешены помимо уже принятого
  прямого manual создания как `published`;
- preview visibility for unpublished content;
- связь block с Media/File.

## 7. Flashcard semantics

Нужно выбрать names/shape `question`/`answer`, optional difficulty, ordering,
status, правила «Знаю/Повторить», API/CMS flow, orphan lifecycle и выдачу
Flashcard без Topic. Nullable Topic relation уже принято; FSRS runtime остаётся
deferred, но current review API зависит от этих semantics.

## 8. Quiz semantics and attempt storage

Нужно решить:

- один или несколько Quiz на Topic;
- Quiz title/description;
- minimum answers and explanation requirement;
- question/answer ordering and answer shuffle;
- difficulty;
- exact compact structure for wrong answers;
- resume model for unfinished attempt;
- whether an attempt may be submitted more than once;
- score rounding and per-question result visibility.

Single-choice, one correct answer, unlimited retake, persisted attempts and no
timeout are already accepted; перечисленные детали — нет.

## 9. Topic completion and progress

Accepted docs allow manual and score-based completion, но threshold и точная
formula не закреплены. Frontend prototype использует 80% and averages theory,
cards and best quiz score.

Нужно выбрать backend source of truth, transition rules for `not_started`,
`learning`, `learned`, reset behavior and whether completion can regress.

## 10. Paywall and subscriptions

Базовая content access model уже принята:

- основной boundary — Topic;
- `access_level = demo | free | paid`;
- `demo` доступен anonymous;
- `free` требует authentication;
- `paid` требует authentication + entitlement;
- отдельные child elements внутри `free`/`paid` Topic могут быть explicit demo preview;
- сложная ACL/inheritance model в MVP не вводится.

Остаётся определить:

- Subscription status machine and overlap rules;
- как конкретные Plan/Tariff дают entitlement к `paid` content;
- trial eligibility/expiration;
- Plan/Subscription retention, cancellation, expiry and account-deletion behavior;
- whether editor/admin bypasses paid access;
- payment provider and webhook boundary.

Plan/Subscription models are required now, provider integration is not.

## 11. Import and bulk operations

Нужно утвердить:

- import identity/upsert keys;
- behavior for removed items on repeated import;
- atomicity (whole file vs per entity);
- admin upload format and error report;
- bulk publish authorization and status transitions;
- synchronous vs background execution.

Until this is decided, no Celery or implicit duplicate-prevention strategy is
added.

## 12. Media storage contract

Нужно выбрать object-storage provider, URL strategy (signed/public), upload
limits, allowed MIME types and cleanup behavior after physical deletion.

## 13. Background jobs

Нужно решить, есть ли в MVP use case, который действительно требует Celery или
другой worker. Пока synchronous services are the default, Redis is cache only,
и новая queue infrastructure запрещена без отдельного решения.
