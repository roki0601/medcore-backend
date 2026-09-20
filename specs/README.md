# MedCore implementation specifications

Approved implementation contracts live here. Existing specs 001–004 describe
already-shipped backend behavior and must not be reopened by a future feature
unless an accepted decision explicitly changes their contract.

## Shipped order

1. [001 — Telegram auth and account](001-telegram-auth-account/spec.md)
2. [002 — Content catalog and access](002-content-catalog-access/spec.md)
3. [004 — Content API and media](004-content-api-media/spec.md)
4. [003 — Learning state](003-learning-state/spec.md)

`004` precedes `003` because learning consumes content-owned
Flashcard/Quiz/Question/Answer entities.

## Future work

Not-yet-specified work is queued under
[`backend-features/`](../backend-features/README.md).

Do not create a numbered implementation spec merely because a roadmap idea
exists. A feature brief must first become implementation-ready.

Current next boundary:

- BE-005 subscriptions/paywall — `READY_FOR_SPEC`, but implementation remains
  blocked by its explicit owner decision packet.

Later BE-006–BE-010 are BLOCKED and should not consume architecture/planning
rounds until their listed prerequisites are resolved.

## Rules

- product decisions: sibling `../medcore-docs/decisions/`;
- backend ownership/architecture: `../docs/architecture/`;
- future roadmap boundary: `../backend-features/`;
- API uses `/api/v1/`, REST, OpenAPI and shared error envelope;
- frontend prototype is not a backend contract;
- a `TBD` is not permission for an agent to choose;
- implementation starts only from an accepted implementation-ready spec;
- plan/tasks should map an accepted contract to code, not redesign the product.
