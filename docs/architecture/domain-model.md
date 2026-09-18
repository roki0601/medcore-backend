# Domain model

Документ фиксирует только сущности и связи, которые влияют на границы
архитектуры. Поля, которые в `medcore-docs` помечены `TBD`, намеренно не
придумываются.

## Ownership map

| Entity | Owning app | Lifecycle owner |
|---|---|---|
| User | `users` | account/auth services |
| Telegram identity | `users` | auth identity service |
| Refresh token/session | `users` | token lifecycle service |
| Subject | `content` | content CMS |
| Section | `content` | content CMS |
| Topic | `content` | content CMS |
| ContentBlockType | `content` | content CMS |
| ContentBlock | `content` | content CMS |
| Flashcard | `content` | content CMS |
| Quiz | `content` | content CMS |
| QuizQuestion | `content` | content CMS |
| QuizAnswer | `content` | content CMS |
| Source | `content` | content CMS |
| Media/File | `media` | media/storage service |
| UserTopicProgress | `learning` | learning services |
| FlashcardReview | `learning` | learning services |
| QuizAttempt | `learning` | learning services |
| Plan/Tariff | `subscriptions` | subscription service |
| Subscription | `subscriptions` | subscription service |

## Relationships and cardinality

```text
Subject 1 ─── N Section 1 ─── N Topic
                              ├── 0..N ContentBlock ─── 1 ContentBlockType
                              ├── 0..N Flashcard
                              └── 0..N Quiz (multiplicity policy TBD)
                                      └── 0..N QuizQuestion (minimum TBD)
                                              └── 1..N QuizAnswer (minimum TBD)

Source 0..N ── M:N ── Topic / ContentBlock / Flashcard / QuizQuestion

Flashcard 0..N ── 0..1 Topic

User 1 ─── 0..N UserTopicProgress ─── 1 Topic
User 1 ─── 0..N FlashcardReview ───── 1 Flashcard
User 1 ─── 0..N QuizAttempt ───────── 1 Quiz
User 1 ─── 0..N Subscription ──────── 1 Plan
User 1 ─── 0..N RefreshToken/Session
```

Следующие cardinalities требуют отдельной фиксации до соответствующих specs:

- какие минимумы нужны для Quiz/QuizQuestion/QuizAnswer и может ли Topic иметь
  больше одного Quiz;
- API/CMS flow, orphan lifecycle и выдача Flashcard без Topic;
- область и uniqueness slug;
- exact relation Media/File с content entities.

## Entity semantics

### User and identities

`User` — владелец аккаунта и всех пользовательских данных. Он поддерживает
уникальный username, Django password hash, optional unique Telegram identity,
optional email, role, active flag и timestamps. Telegram identity и password
credential могут сосуществовать у одного User.

Telegram payload не является User без backend verification.

Refresh token/session принадлежит User, имеет expiration и revocation state.
Сырые refresh tokens не хранятся в БД; конкретный representation для blacklist
определяется auth spec.

### Content hierarchy

`Subject → Section → Topic` — авторская иерархия. Topic принадлежит Section и
косвенно Subject. Учебные элементы внутри Topic optional: пустая тема остаётся
валидной сущностью.

Subject, Section и Topic имеют slug для user-facing URL. Slug генерируется из
title, manual override разрешён, изменение после публикации разрешено на уровне
product decision; redirect/history policy пока не определена.

### ContentBlock

`ContentBlock` — отдельный универсальный блок Topic, а не набор nullable-полей
Topic. Тип блока — отдельная data entity, чтобы добавлять типы без изменения
hardcoded enum в коде. Основной text format — Markdown.

ContentBlock имеет одно из workflow status values `draft`, `generated`,
`reviewed`, `published`. Это набор состояний, а не обязательная линейная
state-machine: manual content может сразу стать `published`, а review flow не
блокирует публикацию на MVP. Полная transition matrix остаётся content-spec
вопросом.

Manual content может сразу стать `published`; AI-imported content получает
`generated`. `reviewed_by` и `published_at` являются частью agreed model
direction. Полная version history не входит в MVP.

### Flashcard

Flashcard — interactive content entity, не ContentBlock. Topic relation optional,
Source relation optional. Self-rating и FSRS runtime не входят в MVP. Для
будущего FSRS допускается хранить current state (`next_review_at`,
`last_reviewed_at`, `repetitions` или эквивалент).

### Quiz

Quiz состоит из QuizQuestion и QuizAnswer. MVP использует single-choice с одним
правильным ответом; ровно четыре варианта на уровне БД не фиксируются. Retake
не ограничен, каждая попытка сохраняется, лучший score вычисляется из attempts.
Timeout и глобальный pass threshold не вводятся.

Полная `QuizAttemptAnswer` на каждый ответ не обязательна; компактная запись
ошибок/неправильных ответов нужна, но точная форма остаётся open question.

### Source and Media/File

`Source` — переиспользуемая optional entity с metadata для учебника,
презентации, статьи, сайта, guideline/methodical material или другого источника.
Удаление Source снимает M2M links и не удаляет учебные entities.

`Media/File` owns metadata, object-storage key/URL и file lifecycle. Binary data
не хранится в PostgreSQL. Content может ссылаться на media, но media не знает
семантику Topic или Learning.

### Learning state

`UserTopicProgress` — unique state на пару `(user, topic)` со статусами
`not_started`, `learning`, `learned`, timestamps открытия/начала/завершения и
данными ручного или автоматического completion.

`FlashcardReview` — одна текущая запись на `(user, flashcard)`. История review
events не обязательна на MVP.

`QuizAttempt` — отдельная попытка пользователя по Quiz, включая незавершённый
progress. Best score отдельно не хранится.

### Subscription and access

`Plan/Tariff` — описание тарифного предложения. `Subscription` принадлежит User
и Plan, хранит status, `starts_at`, `expires_at`, trial-related data при
необходимости и timestamps. Роли и subscriptions независимы.

Subscription policy отвечает за entitlement/capability. Content и Learning не
читают поля Subscription напрямую.

## Lifecycle rules

| Entity group | Create/update | Delete/expiry |
|---|---|---|
| User/auth | services; identity linking is verified | self-delete is required; auth sessions revoke |
| Subject/Section/Topic | Admin/CMS, editor/admin policy | physical deletion on MVP; Topic cascade is explicit |
| ContentBlock | CMS/import workflow | physical deletion; status transition audited by fields |
| Flashcard/Quiz/Source | content CMS/import | Topic cascade; Source detaches links |
| Learning state | created on first user action via service | User deletion cascades progress/attempts |
| Subscription | subscription service | status/expiry changes; retention rules TBD |
| Media/File | media service/admin | storage cleanup policy requires implementation spec |

## Invariants and constraints

- `username` unique;
- `telegram_id`, when present, unique;
- one User may have Telegram and password auth simultaneously;
- passwords are never stored in plaintext;
- one `UserTopicProgress` per user/topic;
- one current `FlashcardReview` per user/flashcard;
- all quiz attempts are retained, best score is derived;
- one correct QuizAnswer per QuizQuestion on MVP;
- no fixed answer count of four;
- all Topic content relations are optional unless a feature spec explicitly
  requires otherwise;
- Topic deletion physically cascades to dependent content and learning data as
  defined by the relevant migration/spec;
- Source deletion removes links only;
- timestamps are timezone-aware and persisted in UTC;
- IDs use Django `BigAutoField`/BigInt direction;
- access is checked backend-side; frontend visibility is not a security boundary;
- database constraints protect uniqueness even when two requests race.

## Deliberately unresolved

Не зафиксированы здесь поля Subject/Section/Topic, slug uniqueness, exact quiz
attempt answer shape, completion threshold, paywall granularity, payment
semantics и storage provider. Полный список — в
[`open-questions.md`](open-questions.md).
