# MedCore implementation specifications

Эти спеки описывают согласованный MVP-контракт backend. Они являются Draft до
отдельного review пользователя; код по ним пока не реализуется.

## Порядок

1. [001 — Telegram auth and account](001-telegram-auth-account/spec.md)
2. [002 — Content catalog and access](002-content-catalog-access/spec.md)
3. [003 — Learning state](003-learning-state/spec.md)
4. [004 — Content API and media](004-content-api-media/spec.md)

После review каждой spec отдельно создаются plan.md и tasks.md через Spec Kit.
Планирование не смешивается с реализацией.

## Общие правила

- Источник продуктовых решений: ../medcore-docs/decisions/, особенно ADR 0008.
- Backend architecture и ownership: docs/architecture/.
- Frontend prototype не является backend-контрактом.
- API использует /api/v1/, REST, OpenAPI и единый error envelope.
- Subscription/payment semantics остаются отдельной будущей спецификацией.
