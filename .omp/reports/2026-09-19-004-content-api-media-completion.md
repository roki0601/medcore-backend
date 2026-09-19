# Отчёт о выполнении: фича 004 — синхронный Content API и защищённые media

- Фича: `004-content-api-media`
- Ветка: `feature/004-content-api-media` (база — `main` @ `d7a9584`)
- Дата: 2026-09-19
- Запись решения: `.omp/decisions/2026-09-19-004-content-api-media-review.md`
- Задачи: `specs/004-content-api-media/tasks.md` (T001–T020 выполнены)
- Статус: `VERIFIED` для реализации и валидации; PR открыт, ручное ревью и
  merge остаются за владельцем
- Коммит фичи: `a1b3781` (в той же ветке далее идут коммиты документации запуска
  и исправление staged-secret проверки)
- PR: https://github.com/roki0601/medcore-backend/pull/6
- Спека: `specs/004-content-api-media/spec.md` приведена к согласованному
  контракту (статус `Approved for implementation`)

## Preflight

Все три репозитория были чистыми и fast-forward на выбранных ветках до
создания feature-ветки:

| Репозиторий | Ветка | HEAD |
|---|---|---|
| `medcore-docs` | `main` | `0b1d51c` |
| `medcore-backend` | `main` | `d7a9584` |
| `medcore-frontend` | `main` | `db3473d` |

`PROJECT_STATE.md` всё ещё требовал ручного merge PR #5 по фиче 002; PR
`MERGED`, и `main` содержит его merge-коммит `d7a9584`, поэтому гейт снят как
устаревший. `PROJECT_STATE.md` обновлён этим запуском.

## Вердикты ревью

| Роль | Модель | Вердикт |
|---|---|---|
| DeepSeek manager (source-backed review спеки) | `openrouter/deepseek/deepseek-v4.1-flash` (`@plan`) | `READY_FOR_PLAN` после записи решения и правок спеки |
| Luna `watchdog` (раунд 1) | `openai-codex/gpt-5.6-luna` (`high`) | `BLOCKED` по пунктам 3 и 8; `RESOLVED` по 1, 2, 4, 6, 7 и условно 5 |
| Luna `watchdog` (раунд 2) | `openai-codex/gpt-5.6-luna` (`high`) | `BLOCKED` по пунктам 3 и 5 — оба закрыты предложенными Luna же средствами (сохранён `SET_NULL` + race-safe orchestration; immutable-content policy без удаления детей) |
| DeepSeek `senior-reviewer` | `openrouter/deepseek/deepseek-v4.1-flash` (`max`) | `BLOCKED` на одном дефекте (достижимый publish-путь не брал блокировку строки `MediaFile`); после исправления и регрессионного теста блокер закрыт |
| DeepSeek `security-reviewer` | `openrouter/deepseek/deepseek-v4.1-flash` | `READY`, эксплуатируемых дефектов нет; 5 замечаний low/informational, четыре закрыты кодом, одно принято как residual risk |

## Поставленный объём

- `apps/content/models.py`, `migrations/0003_content_api_entities.py` —
  `external_id` на пяти сущностях 002, новые `Flashcard`, `Quiz`,
  `QuizQuestion`, `QuizAnswer`, M2M `Source.flashcards`/`Source.questions`,
  `(parent, position)` уникальность; `ContentBlock.media` оставлен `SET_NULL`.
- `apps/content/services.py` — identity-резолвинг `external_id` (upsert,
  неизменяемость, 409), семь `upsert_*`, агрегатная запись quiz
  (сохранение id, отсутствие удаления детей, минимумы), сервисы удаления с
  `ProtectedError → 409`, блокировка строки `MediaFile` в `save_content_block`
  и `publish_content_block`.
- `apps/content/serializers.py`, `views.py`, `urls.py` — строгие write-сериализаторы
  (неизвестные поля → 422), authoring read-сериализаторы, 14 маршрутов
  `/api/v1/content/` с правами integration key | editor/admin и OpenAPI.
- `apps/content/media_policy.py` — `decide_media_access` (композиция доступа 002
  + demo-preview) и `guard_media_deletion` (409 при published-ссылке).
- `apps/media/storage.py` — `StorageAdapter`, `LocalStorageAdapter`
  (capability-URL upload/download, sidecar метаданных), `S3StorageAdapter`
  (presigned URL, `head_object`, `ContentLength` в подписи), резолвер из настроек.
- `apps/media/services.py`, `serializers.py`, `views.py`, `urls.py`, `checks.py`,
  `admin.py` — CRUD метаданных, проверка загрузки (размер/checksum), выдача
  upload/access URL с решением о доступе до обращения к хранилищу, guard при
  удалении с `transaction.on_commit`, шесть маршрутов `/api/v1/media/`,
  системная проверка `media.E001` (local backend вне `DEBUG`), staff+role гейт.
- `apps/common/integration.py`, `permissions.py` — аутентификация по integration
  key (constant-time, только маркированные маршруты, non-User principal),
  `HasIntegrationKey`, `IsContentAuthor`, `IsNotIntegrationClient`.
- `config/settings/base.py`, `.env.example`, `config/urls.py`, `pyproject.toml`
  (+ optional extra `storage-s3`), `uv.lock` — настройки, лимиты, TTL,
  throttle-скоупы `integration_write`/`media_upload`/`media_metadata`/`media_access`.
- `docs/architecture/domain-model.md` — исправлен устаревший инвариант
  «один правильный ответ» и закрыты cardinality-TBD со ссылкой на запись решения.
- `specs/004-content-api-media/*` — спека, план, research, data-model, два
  контракта, quickstart, tasks; `specs/README.md` — порядок 001→002→004→003.

## Валидация (точные команды, финальное дерево)

```text
$ uv run ruff format --check .
163 files already formatted

$ uv run ruff check .
All checks passed!

$ uv run pytest -q
244 passed in 8.46s

$ uv run python manage.py check
System check identified no issues (0 silenced).

$ uv run python manage.py makemigrations --check --dry-run
No changes detected

$ DJANGO_SETTINGS_MODULE=config.settings.base DJANGO_DEBUG=false uv run python manage.py check
SystemCheckError: (media.E001) local storage backend refused outside DEBUG
```

## Доказательства невакуумности и живые прогоны

- **Quickstart-smoke (live PostgreSQL + Redis + runserver, local backend):**
  41/41 проверок пройдено (матрица integration key/JWT, strict payloads,
  `external_id` upsert, агрегат quiz со стабильными id, upload/download по
  capability-URL, матрица доступа к media, истечение подписанной ссылки,
  guard удаления и repair, каскад удаления Topic с сохранением соседей,
  OpenAPI). Скрипт был одноразовым и удалён; данные и пользователи вычищены
  (проверено запросами к БД: 0 остатков).
- **Live MinIO (S3-compatible) прогон:** 10/10 проверок — presigned upload с
  привязанным `ContentLength`, `head_object`-верификация, отказ второго
  upload-контракта (409), presigned access URL, побайтовое скачивание,
  422 при расхождении размера, удаление и очистка объекта в бакете.
  Контейнер MinIO был одноразовым и удалён, в `compose.yaml` ничего не добавлено.
- **Регрессионный тест блокера:** тест гонки «publish против delete» падает при
  откате блокировки строки `MediaFile` в `save_content_block` и проходит с ней.
- **Секреты:** staged-diff просканирован вручную (эквивалент
  `scripts/ai/check-git-safety.sh`, т.к. в окружении нет `rg`); реальные ключи,
  JWT, cookies и токены Telegram в коммит не попали.

## Нерешённые риски и наблюдения

- **Провайдер object storage всё ещё не выбран.** Локальный backend — только
  dev/test и запрещён вне `DEBUG` системной проверкой; production-загрузка
  требует настройки S3-compatible backend. S3-адаптер проверен на одноразовом
  MinIO, а не на production-бакете.
- **Capability-токен локального backend передаётся в path URL**, поэтому
  deployment обязан исключить префиксы `/api/v1/media/upload/` и
  `/api/v1/media/file/` из access-логов; TTL 600 с, приложение токен не логирует.
- **Presigned URL S3 содержит object key** — бакет обязан оставаться приватным.
- **`paid`-медиа недоступна до появления источника entitlement**: deny-путь
  реальный, allow-путь доказан через policy seam (`has_paid_content_entitlement`).
- **Дети quiz неизменяемы по идентичности** (создание/обновление, без удаления) —
  сознательное сужение, зафиксированное в записи решения; политика удаления
  агрегата и попыток остаётся за спекой 003.
- **Ревизия Luna:** итоговый вердикт раунда 2 был `BLOCKED`; оба блокера закрыты
  средствами, которые Luna сама назвала, третий раунд не запускался (бюджет —
  два ограниченных раунда). Человеческий ревьюер может переоткрыть пункты 3 и 5.
- **Обнаружен и исправлен дефект проектного tooling:** `scripts/ai/check-git-safety.sh`
  использовал `rg`, которого в окружении нет, из-за чего проверка staged-секретов
  молча не выполнялась. Заменено на `grep -E` отдельным коммитом; на фичу не влияет.

## Следующее действие

Отревьюить PR https://github.com/roki0601/medcore-backend/pull/6 и выполнить
merge вручную. Из OMP-запуска merge не делается и `main` не пушится. После
merge следующая фича — `003-learning-state` (она использует сущности контента,
поставленные 004).
