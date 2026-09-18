# Current state

Статус среза: 2026-09-18.

Этот документ описывает фактическое состояние `medcore-backend`, а не желаемый
результат. Целевая backend-архитектура находится в
[`target-architecture.md`](target-architecture.md).

## Краткий вывод

Backend ещё не реализован. В репозитории нет Django-проекта, зависимостей,
моделей, API, auth, migrations, tests, Docker-конфигурации или CI. Единственный
tracked-файл с описанием backend — минимальный `README.md`.

Следовательно, ниже нельзя ссылаться на существующие implementation patterns:
их пока нет. Документы из `medcore-docs` описывают продукт и согласованные
решения, но не доказывают наличие соответствующего кода.

## Что реально есть в backend-репозитории

| Область | Фактическое состояние |
|---|---|
| Django project | отсутствует; нет `manage.py`, `config/`, settings, ASGI/WSGI |
| Django apps | отсутствуют |
| Models / migrations | отсутствуют |
| REST API | отсутствует |
| Authentication / permissions | отсутствуют |
| Dependencies | нет `pyproject.toml`, `uv.lock` и requirements-файлов |
| Tests | отсутствуют |
| Infrastructure | нет Dockerfile, compose, env example, CI |
| Documentation | только начальный `README.md`; архитектурные документы создаются этим изменением |
| Local tooling | `.serena/` не tracked и не является частью backend-контракта |

Проверки Django, pytest и lint невозможно запустить содержательно: проект и
команды ещё не существуют.

## Контекст из соседних репозиториев

`medcore-docs` — отдельный репозиторий с продуктовым и архитектурным
контекстом. Он является источником принятых продуктовых решений до тех пор,
пока новое решение явно не оформлено. Особенно важны:

- `decisions/0004-mvp-decision-register.md` — 200 пунктов, из которых часть
  явно помечена `TBD`;
- `decisions/0005-decision-register-audit.md` — уточняет приоритет решений и
  политику работы с `TBD`;
- `architecture/overview.md` — общая схема runtime;
- `architecture/backend-structure.md` — рабочий draft границ Django apps и
  слоёв;
- `architecture/database.md` — рабочий draft сущностей и связей;
- `ai/context.md` и `AGENTS.md` — правила для AI-агентов;
- `product/mvp.md`, `content/*` — MVP и контентный workflow.

`medcore-frontend` содержит статический prototype «Кафедра». В нём данные и
прогресс живут в JavaScript/localStorage, auth имитируется на клиенте, сервера
нет. Это поведенческий референс, а не реализованный API или схема backend.

## Уже принятые решения, которые должны быть сохранены

- отдельные Next.js frontend и Django + DRF backend;
- modular monolith, PostgreSQL как primary datastore, Redis для cache;
- Python 3.12, `uv`, Ruff/Ruff format, pytest;
- REST API с prefix `/api/v1/`, Bearer JWT;
- access token + refresh token в `httpOnly` cookie, refresh revocation/blacklist;
- Telegram — основной auth flow, login/password — резервный; один User может
  иметь оба способа входа;
- роли `user`, `editor`, `admin`; подписка не является ролью;
- `Subject → Section → Topic`;
- `ContentBlock` — отдельная гибкая сущность с типом, хранимым в БД;
- Flashcard и Quiz — отдельные interactive entities, не ContentBlock;
- Markdown для текстового контента;
- статусы контента `draft`, `generated`, `reviewed`, `published`;
- optional sources, отдельная Media/File model и object storage;
- topic progress, flashcard review state и quiz attempts принадлежат learning;
- физическое удаление на MVP с согласованным каскадным поведением;
- Django Admin как CMS, bulk import и bulk publish нужны;
- backend сам проверяет paywall/access;
- search MVP через PostgreSQL/Django `icontains` по названиям;
- OpenAPI/Swagger, throttling, ограниченный CORS и технические логи;
- Celery, payment provider и конкретный object storage provider остаются
  unresolved/TBD.
- Elasticsearch/OpenSearch, FSRS runtime, product event analytics, Sentry,
  staging и user-facing AI/voice features явно deferred/out of MVP; это не
  implementation blockers для первой backend foundation.

## Draft и legacy, которые нельзя выдавать за реализацию

`architecture/backend-structure.md` и `architecture/database.md` прямо имеют
статус draft. Их полезные границы перенесены в target-документы, а их
неразрешённые пункты сохранены в `open-questions.md`.

Frontend prototype содержит локальные/временные решения:

- email является обязательным полем его demo auth, тогда как backend decision
  register фиксирует уникальный `username`, а email оставляет optional;
- guest может временно видеть ограниченные части контента, тогда как accepted
  MVP decision говорит «контент только для authenticated users»;
- frontend хранит строковые demo IDs и прогресс в localStorage;
- frontend использует формулу прогресса и порог 80%, но backend threshold и
  точная domain-модель ещё не утверждены.

Эти расхождения — не повод молча выбрать вариант. Они вынесены в
`open-questions.md` и должны быть закрыты отдельными feature specs или
решением владельца продукта.

## Что следует считать source of truth

1. Явно принятые product/architecture decisions в `medcore-docs`, прежде всего
   `0004` и более новый `0005`.
2. Этот каталог `docs/architecture/` — backend-specific architecture,
   domain ownership и engineering conventions.
3. Конкретная feature specification — точный scope и API/data contract
   конкретной фичи.
4. Existing code/tests — только после появления реализации и при условии, что
   конфликт с docs эскалирован, а не принят молча.

## Итог для следующего этапа

Нельзя начинать реализацию с «починки существующего backend»: исправлять пока
нечего. Следующая модель должна сначала создать project skeleton и закрыть
foundation/auth contracts по feature specs, не притворяясь, что prototype или
draft-документ уже является работающим API.
