# Отчёт о завершении: OpenAPI-контракт для frontend client

- Статус: `VERIFIED`
- Ветка: `codex/fix-openapi-contract`, база `main@0ee924b`
- Scope: только schema metadata, typed serializers, OpenAPI tests и OMP state
- Frontend не инспектировался и не изменялся: это отдельный репозиторий вне backend OMP scope
- Предыдущий PR: feature 003 уже merged, PR #9, merge commit `0ee924b`

## Цель

Закрыть расхождения между фактическим backend runtime и generated OpenAPI,
которые могли блокировать frontend client: общий error envelope, typed
learning/media/auth payloads и явные security schemes.

## Делегирование Luna Max

Все subagents в этом запуске использовали `gpt-5.6-luna` с максимальным
reasoning effort:

- `pr-auditor` — независимый аудит merged feature 003: blocker не найден;
- `integration-reviewer` — обнаружил OpenAPI contract gaps;
- `researcher/architect` — подтвердил `subscriptions/paywall` как
  `READY_FOR_SPEC`, а не implementation-ready;
- `implementer-openapi-contract` — production-правка в ограниченной schema-зоне;
- `final-reviewer` — сначала нашёл два P1, после исправлений дал `READY`.

## Изменения

- Добавлен `APIErrorResponseSerializer` и response schema `{code, detail, fields}`
  для documented 4xx responses.
- Зарегистрирован `integrationKeyAuth` для
  `X-MedCore-Integration-Key`; drf-spectacular больше не теряет authoring auth
  scheme.
- Описаны `QuizAttempt.question_ids` и `QuizAttemptResult` как typed arrays,
  `AuthTokenResponse.user` сделан обязательным.
- `ContentBlock.media` получил typed `MediaReference` и `nullable: true`.
- Media access URL документирует anonymous OR Bearer security; runtime policy не
  менялась.
- Write maps для content/learning/media документируют возможный `400`
  `APIErrorResponse`.
- Добавлены regression tests в
  `apps/common/tests/test_openapi_contract.py`.

## Проверки

```text
uv run pytest apps/common/tests/test_openapi_contract.py -q  -> 4 passed
uv run pytest -q                                           -> 365 passed
uv run ruff format --check .                               -> 207 files already formatted
uv run ruff check .                                        -> All checks passed!
uv run python manage.py check                              -> no issues
uv run python manage.py makemigrations --check --dry-run   -> No changes detected
uv run python manage.py spectacular --file /tmp/medcore-openapi-validated.yml --validate
  -> Errors: 0; 2 non-blocking enum-name collision warnings
git diff --check                                            -> clean
```

Independent final review: `READY`; runtime payloads, permissions, migrations,
dependencies and circular-import behavior unchanged.

## Не вошло в scope

Оставлены отдельными follow-up замечаниями из аудита feature 003: лимит
`selected_answer_ids <= 500`, полная materialization pagination и раздельная
transaction boundary для комбинированного progress PATCH. Они требуют
отдельного contract/implementation решения и не относятся к frontend OpenAPI
blocker.

## Следующее действие

После atomic commit этого follow-up подготовить implementation-ready
subscriptions/paywall spec. До её approval не добавлять модели, API или
entitlement semantics: остаются TBD status machine, plan-to-entitlement
mapping, trial, expiry/retention/account deletion и payment/webhook boundary.
