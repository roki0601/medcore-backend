# Отчёт о завершении: `003-learning-state`

- Статус: `VERIFIED` (реализация + валидация + live smoke); PR открыт, требуется ручной
  review/merge
- Ветка: `feature/003-learning-state` от `f30b1e4` (`main`)
- Коммит фичи: `1e5bf5d` `feat(learning): add progress, flashcard review and quiz attempts`
- PR: https://github.com/roki0601/medcore-backend/pull/9 (open, merge из OMP не делается)
- Решение: `.omp/decisions/2026-09-19-003-learning-state-review.md`
- Спека/план: `specs/003-learning-state/{spec,plan,tasks,research,data-model,quickstart}.md`,
  `contracts/learning-api.md`

## Что вошло в фичу

`apps/learning` перестал быть skeleton: четыре модели (`UserTopicProgress`,
`UserTopicBlockProgress`, `FlashcardReview`, `QuizAttempt`), миграция `0001_initial`,
общие хелперы (`access.py`, `services.py`, `scheduling.py`, `scoring.py`,
`serializers.py`) и три поддомена с раздельными urls/selectors/services/serializers/views
(`progress/`, `flashcards/`, `quizzes/`) — всего 11 аутентифицированных маршрутов
`/api/v1/`. Теория темы — published `ContentBlock`; попытка фиксирует набор вопросов на
старте и замораживает результат на submit; до submit `is_correct` не отдаётся; `paid`-темы
остаются за `subscriptions.policy`; порог прохождения и score-based авто-завершение не
реализованы (register item 65 + открытое решение владельца).

## Процесс и воркеры

Планируемое и фактическое число воркеров: 1 foundation (волна 1) + 3 параллельных
фича-зоны (волна 2) + 1 fixes-воркер (после ревью) = 5 пишущих воркеров; отдельно 3
read-only прохода (`scout`-инвентаризация ×3, `spec-reviewer` consistency, `senior-reviewer`,
`security-reviewer`) и 1 Luna-watchdog.

| Зона / проход | Параллельная группа | Длительность | Целевая проверка |
|---|---|---:|---|
| `Z1-foundation` | 1 (блокирующая) | 35m15s | `pytest test_models/test_scheduling/test_scoring` — 42 passed, 0.56s |
| `Z2-progress` | 2 | 15m00s | `pytest test_progress_api.py` — прошло |
| `Z3-flashcards` | 2 | 16m35s | `pytest test_flashcards_api.py` — 15 passed, 0.68s |
| `Z4-quizzes` | 2 | 33m47s | `pytest test_quizzes_api.py` — прошло |
| senior review | 3 | 17m34s | read-only |
| security review | 3 | 23m51s | read-only |
| `Z5-fixes` | 4 | 42m25s | `pytest` по затронутым файлам — прошло |

Критический путь: `Z1-foundation` (35m15s) → `Z4-quizzes` (33m47s) → `Z5-fixes` (42m25s),
≈ 1h51m; ожиданий интеграции не было (файлы зон не пересекались, единственный
последовательный гейт — foundation). Плюс read-only фазы: Luna spec review 7m52s,
consistency analysis 20m27s.

## Проверки (единый проект-wide проход после интеграции)

```text
$ uv run ruff format --check .                             -> 204 files already formatted
$ uv run ruff check .                                      -> All checks passed!
$ uv run pytest -q                                         -> 361 passed in 15.47s
$ uv run python manage.py check                            -> System check identified no issues (0 silenced).
$ uv run python manage.py makemigrations --check --dry-run  -> No changes detected
```

- До фиксов: 349 passed; после закрытия ревью-находок и добавления тестов — 361
  (117 learning-тестов).
- Live smoke на живых PostgreSQL 17.4 / Redis / `runserver` (скрипт-одноразовик вне
  репозитория, удалён после прогона): **64/64** проверок — 401/403/404-матрица,
  прогресс и идемпотентность 201/200, `learned` без регресса, расписание карточек
  `1→3→7` и `repeat`, due-список, старт/резюм/submit/retake, отсутствие `is_correct`
  до submit, `is_correct`-flip после старта влияет на submit и не переписывает
  отправленные попытки, 409 на повторный submit/PATCH, `best_score_percent`,
  11 путей в OpenAPI-схеме, 429 при throttling, каскад при удалении темы.
- Ранее (до доработок) полный smoke дал 63/64: единственный FAIL был ошибкой самого
  smoke-скрипта (`?format=openapi-json` не поддерживается этим drf-spectacular — 404), а
  не дефектом фичи; проверка схемы переведена на разбор YAML.
- CI GitHub Actions (workflow `CI`, run `35455508683`, job `quality`, head `8e615f4`):
  `success` — форматирование, линт, Django-проверки, проверка миграций и pytest на
  PostgreSQL 16 + Redis 7.

## Тесты и rationale

| Файл | Тестов | Зачем |
|---|---:|---|
| `test_models.py` | 14 | инварианты БД и матрица каскадов (User/Topic/Block/Flashcard/Quiz), частичный unique активной попытки, bounds скора |
| `test_scheduling.py` | 14 | матрица расписания: первый `know`, шаг на интервал, sticky-последний, reset, переопределение настроек |
| `test_scoring.py` | 14 | числовой контракт: частичный балл, нулевой пол, неотвеченный вопрос, одно округление, display-округление не восстанавливает итог |
| `test_progress_api.py` | 23 | границы процента, идемпотентность, `GET` не пишет, переходы и не-регресс `learned`, 404/403/422/401, перенос блока, гонка `opened` × `learned` |
| `test_flashcards_api.py` | 18 | расписание через API, одна текущая строка, переход темы в `learning`, due-фильтр, валидация, гонки создания и двойного `know` |
| `test_quizzes_api.py` | 32 | жизненный цикл попытки, контракт ошибок, скоринг через API, политика grading, отсутствие утечки `is_correct`, ретейки, best score, гонки start/submit |
| `test_openapi.py` | 2 | схема содержит 11 learning-путей и ни одного `is_correct` в компонентах |

## Ревью-вердикты

- `spec-reviewer` (consistency analysis, `ANALYZED`): `NOT_READY` — 1 `BLOCKER` (порог 80 %
  как изобретённый параметр, противоречащий register item 65) + 8 `HIGH`. Все закрыты:
  `passed`/порог убраны, действие с карточкой переводит тему в `learning`, анонимное
  чтение quiz запрещено (записано как сужение), `UserTopicBlockProgress` без `topic`,
  таблицы зон унифицированы, URL-склейка переведена в foundation-шаг, grading-политика
  покрыта тестом, коды ошибок выровнены.
- Luna `watchdog` (round 1, `BLOCKED` по Q2.1/Q2.7): форма `answers_state` (только answer
  ID) закреплена отдельными полями `question_ids`/`results`, авто-завершение по score
  отложено явной записью.
- `senior-reviewer`: `BLOCKED` — гонка review без row lock (существующий тест её не
  ловил). Исправлено `select_for_update` + тест, падающий при откате (`3 != 7`).
- `security-reviewer`: `READY`, эксплуатируемых дефектов нет; тот же lost update + откат
  `learned` без условного UPDATE + неограниченный список answer ID — все закрыты, включая
  500 на `OPTIONS/HEAD` и неизвестные поля на пустых POST-телах.

## Остаточные риски (приняты, не блокируют)

- Порог прохождения, pass/fail и score-based авто-завершение темы — открытое решение
  владельца (register items 65, 67-68).
- Изменение `is_correct` во время активной попытки меняет её grading; отправленные попытки
  воспроизводимы (решение Luna round 1 «RESOLVED»).
- После первого submit `results` раскрывают правильные ответы, ретейки не ограничены
  (принято контрактом; при нежелательности — не отдавать `correct_answer_ids` или
  ограничить ретейки).
- `paid`-темы недоступны до фичи подписок; deny-путь реальный, allow-путь доказуем через
  policy seam.
- Канонические `medcore-docs` не менялись: отложенные пункты остаются открытыми владельцу.

## Следующее действие

1. Ручное ревью и merge PR #9 (OMP merge не выполняет).
2. Решение владельца по порогу прохождения (он же разблокирует авто-завершение темы).
3. Следующая фича — subscriptions/paywall: источник entitlement для `paid` контента и
   медиа.