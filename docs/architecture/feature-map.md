# Feature map

Карта показывает функциональные области, их owning app и контекст будущих
feature specs. Сейчас здесь нет подробных specs, кроме
[`../example-spec.md`](../example-spec.md), которая является эталоном только
для password/JWT auth slice.

## Functional areas

| Area | Purpose | Owning app | Main entities | Dependencies | Spec must define |
|---|---|---|---|---|---|
| Foundation/API | project boot, settings, health, versioning, error envelope, OpenAPI | `config` + `common` | request context, API error | PostgreSQL, Redis, DRF | setup/env, settings split, health contract, CORS, throttling, checks |
| Password auth and account | registration, login, JWT, refresh, logout, account lifecycle | `users` | User, RefreshToken/Session | `common` | identifier, payloads, token lifecycle, CSRF, revoke, errors, deletion |
| Telegram auth | verified Telegram login and account linking | `users` | User + Telegram identity | Telegram | verification protocol, deduplication, linking/unlinking, throttling |
| User profile/preferences | profile data and study preferences, if included in MVP | `users` if approved | User, profile/preferences if approved | `users` | first decide MVP scope/owner, then fields, privacy and update semantics |
| Content hierarchy | catalog of subjects, sections and topics | `content` | Subject, Section, Topic | `users` for author/audit; `subscriptions.policy` at application boundary | fields, slugs, ordering, publish visibility, deletion |
| Theory/content blocks | Markdown blocks and status workflow | `content` | ContentBlockType, ContentBlock, Source | `media`, `users` | type registry, ordering, raw HTML, review/publish transitions |
| Media/files | file metadata and object storage | `media` | Media/File | object storage provider | upload/download, ownership, URLs, cleanup, limits |
| Content import/CMS | normalized JSON import, upsert and bulk publish | `content` | import payload + content entities | `media`, `users` | identity/upsert, atomicity, error reporting, admin permissions, sync/async |
| Access/subscriptions | free content, plans, trial, paid entitlements | `subscriptions` | Plan/Tariff, Subscription | `users`, application access boundary | status machine, overlap, trial, granularity, payment boundary |
| Theory progress | read/complete topic and derived progress | `learning` | UserTopicProgress | `users`, `content`, `subscriptions.policy` | status transitions, manual/score completion, threshold, concurrency |
| Flashcards | serve cards and persist current review state | `learning` + `content` | Flashcard, FlashcardReview | `users`, `content`, `subscriptions.policy` | known/repeat semantics, ordering, optional topic, FSRS placeholder |
| Quizzes | take, resume, submit and inspect attempts | `learning` + `content` | Quiz, Question, Answer, QuizAttempt | `users`, `content`, `subscriptions.policy` | cardinality, options, wrong-answer storage, resume, scoring, retries |
| Search | title search and subject/section filters | `content` | Subject, Section, Topic | PostgreSQL, `subscriptions.policy` | query scope, pagination, access filtering, ranking expectations |
| Progress/dashboard | home, progress, weak topics and aggregates; activity details only if separately approved | `learning` | derived progress/activity | `content`, `users`, `subscriptions.policy` | decide backend activity scope, source of truth, aggregation, retention, API shape |
| Admin/roles | editor/admin capabilities and audit surface | `users` + owning apps | roles, admin history | Django Admin | role matrix, object-level boundaries, audit expectations |

## Dependency notes

- `content` owns authoring entities; `learning` owns user state around them.
- `subscriptions` owns entitlement policy; content/learning do not inspect
  Subscription fields directly.
- `media` is infrastructure-facing and does not own content meaning.
- Telegram and object storage are adapters behind their owning apps.
- Payment provider is not a prerequisite for creating Plan/Subscription models,
  but no provider integration should be invented before its spec.
- Background workers are not assumed by import, notifications or analytics.

## Recommended implementation/spec order

1. **Foundation/API bootstrap** — make the empty repository runnable and fix
   settings, database, Redis cache, errors, health, OpenAPI and checks.
2. **Password auth/account** — establish custom User, permissions and token
   lifecycle before any user-owned state.
3. **Telegram auth** — add the verified identity flow after the base account
   contract is stable.
4. **Media/storage boundary** — needed by content figures/files without coupling
   content to a provider.
5. **Content hierarchy** — Subject/Section/Topic, slugs, CMS and published read
   access.
6. **Content blocks and sources** — Markdown, statuses, review/publish and
   source links.
7. **Subscriptions/access policy** — free/paid capability before exposing all
   content endpoints.
8. **Theory progress** — UserTopicProgress and manual completion.
9. **Flashcards** — content delivery plus one current review state.
10. **Quizzes** — attempts, resume, scoring and wrong-answer representation.
11. **Search and aggregate/dashboard APIs** — compose stable domain selectors and
    access rules.
12. **Import/bulk operations and hardening** — only after entity contracts and
    idempotency identity are fixed.

Каждый пункт должен быть отдельной implementation-ready spec с acceptance
criteria. Порядок не означает, что все решения уже приняты: open questions
блокируют соответствующий spec, а не решаются coding-agent самостоятельно.
