# Authentication and access

## Scope and vocabulary

- Authentication отвечает, кто пользователь.
- Role permission отвечает, разрешена ли операция его роли.
- Access policy отвечает, доступен ли продуктовый ресурс по free/subscription/trial.
- Domain invariant отвечает, допустима ли операция по состоянию сущности.

Эти проверки не объединяются в один `is_premium` flag.

## Authentication methods

### Telegram

Telegram — основной пользовательский auth flow. Backend обязан сам проверить
подлинность Telegram identity и не должен считать frontend-provided `telegram_id`
доказательством личности. Минимально сохраняются verified `telegram_id` и
Telegram username.

### Login/password

Login/password — резервный auth flow. Password хранится только через Django
password hashing. Один User может одновременно иметь Telegram identity и
password credential.

Текущий backend decision register фиксирует unique `username` и optional email.
Для password flow target-контрактом этого backend-пакета является вход по
username; email остаётся optional и не является alias login. Frontend prototype
использует email как обязательный demo login; это prototype-only расхождение,
которое frontend должен адаптировать к backend contract.

## Anonymous access

Всегда доступны без User:

- healthcheck;
- auth entry points, которые по смыслу работают до входа;
- OpenAPI только если deployment policy разрешает его публичность.

Accepted MVP direction говорит, что учебный контент доступен только
authenticated users. Frontend prototype показывает ограниченный guest flow, но
prototype не расширяет backend contract: anonymous content requests запрещены.

## Roles

| Role | Own capability |
|---|---|
| `user` | читать разрешённый контент, менять свой account, создавать и видеть свой learning state |
| `editor` | всё пользовательское + создавать/редактировать/публиковать контент в пределах editor policy |
| `admin` | полный backend/admin access, включая users/system configuration по отдельным safeguards |

`premium` не роль. Наличие Subscription/Plan проверяется отдельной access
policy. Editor/admin role сама по себе не должна незаметно означать premium для
пользовательского API; это нужно явно определить в paywall spec.

## Ownership permissions

- User может читать/изменять только собственный профиль и account settings.
- User может читать/изменять только собственный progress, reviews и attempts.
- Editor не управляет пользователями, ролями, refresh sessions или системными
  настройками.
- Admin permissions не должны даваться обычному editor через frontend flag.
- Published content read policy применяется после authentication и access check.
- User-facing API не должен публиковать `draft`/`generated`/`reviewed` content,
  пока отдельная content spec явно не определит preview capability. Это default
  security boundary, а не решение о CMS preview UX.

## JWT contract

### Access token

- передаётся в `Authorization: Bearer <access_token>`;
- содержит минимальные claims для User identity/expiry и не содержит password,
  Telegram secret или subscription dump;
- короткоживущий и не хранится в PostgreSQL как обычная session record;
- истечение даёт `401`, frontend получает новый access через refresh flow.

### Refresh token

- хранится в `httpOnly` cookie;
- cookie должна иметь `Secure` в production и явный `SameSite`/domain policy;
- текущий план Render/Vercel не является автоматически поддерживаемой cookie
  topology: production auth требует sibling custom domains под одним site или
  same-origin proxy/BFF; `SameSite=None` сам по себе не решает third-party cookie
  blocking;
- refresh token/session имеет expiration и persistent revocation state;
- logout и security-sensitive account changes revoke token(s);
- raw refresh token не логируется и не хранится в базе.

Example password/JWT spec использует non-rotating refresh token с persistent
revocation record как локальный контракт этого примера. Глобальная
rotation/reuse policy для всех auth flows остаётся open question до отдельного
решения. Требование revocation/blacklist не может быть убрано ради простоты.

## Token lifecycle

1. Registration/login создаёт или находит User согласно auth rules, выдаёт
   access token и refresh cookie.
2. Refresh проверяет signature, expiry, token type, User active state и
   revocation state.
3. Logout отзывает текущий refresh token/session и очищает cookie.
4. Password change, self-delete и другие security-sensitive операции отзывают
   затронутые refresh sessions.
5. Deactivated/deleted User не может refresh или использовать API.

Cookie-authenticated state-changing endpoints должны быть защищены от CSRF;
`httpOnly` сам по себе CSRF-защитой не является. CORS, trusted origins и CSRF
policy настраиваются согласованно с frontend deployment.

## API permission layers

```text
request
  ├─ authentication (JWT / anonymous)
  ├─ role permission (user/editor/admin)
  ├─ access policy (free/subscription/trial)
  └─ domain service invariants
```

DRF permission classes подходят для coarse role/identity checks. Resource-level
и paywall checks выполняются через application service/policy boundary, а не
только в frontend и не в model `save()`. Выбор global `IsAuthenticated` или
endpoint-specific default остаётся TBD; до его закрытия каждая feature spec
обязана явно указать permission для каждого endpoint. Accepted baseline для
учебного контента — authentication required; healthcheck и auth entry points
явно public.

## Security requirements

- login errors не раскрывают, существует ли username. Registration возвращает
  deterministic conflict для уже занятого username как явный contract этого
  backend slice; throttling и rate limits ограничивают abuse этого endpoint;
- не логировать passwords, JWT, cookie values и Telegram verification secrets;
- throttling обязателен для login, registration, refresh и Telegram verification;
- CORS ограничен frontend origins;
- password policy и reset/change flows описываются в auth specs;
- account deletion выполняется через service и транзакционно отзывает sessions;
- технические auth errors логируются с request/user context без секретов.

## Open auth decisions

Точный Telegram handshake, account linking/deduplication и password reset
delivery не выдумываются этим документом. Они перечислены в
[`open-questions.md`](open-questions.md), а до решения не должны появляться как
неявные assumptions в коде. Password username login зафиксирован target/example
spec; refresh rotation и global permission default остаются отдельными
архитектурными вопросами.
