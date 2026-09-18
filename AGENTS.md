# AGENTS.md

## Project role

`medcore-backend` is the Django/DRF backend of MedCore. The backend foundation
already exists and product features are implemented incrementally from approved specs. Product and architecture decisions are documented;
coding agents implement approved specs and do not invent the system design while
coding.

## Source of truth

Use this precedence:

1. Explicit accepted decisions in the sibling `medcore-docs` repository,
   especially `decisions/0004-mvp-decision-register.md` and newer decisions.
2. Backend-specific architecture and conventions in
   `docs/architecture/` (these documents must conform to accepted decisions).
3. The relevant approved implementation-ready feature spec; a feature spec may
   refine an implementation contract but cannot silently override architecture
   or an accepted decision.
4. Existing code and tests, once they exist.

`TBD` means unresolved. It is not permission to choose a product or architecture
decision silently. If code, spec and accepted decision conflict, report the
conflict and stop the affected change until the owner resolves it.

## Before implementation

The agent must read:

1. this file;
2. relevant `docs/architecture/*` documents;
3. the sibling `medcore-docs/ai/context.md`, `AGENTS.md`, product context and
   accepted decision register;
4. all related ADRs/decision documents, including newer overrides;
5. the complete approved relevant feature spec;
6. existing code/tests in the owning app.

The agent must identify the owning Django app, affected entities, dependency
direction, API contract, risks and validation commands before editing.

## Architecture guardrails

- `docs/architecture/` is the backend architecture source of truth.
- Do not independently change architectural style, app ownership, domain
  boundaries, auth/token semantics, permissions, public API, data model or
  infrastructure choices.
- Do not expand a task because a broader refactor seems cleaner.
- Do not make optional content required, close a `TBD`, or add a new domain app
  without an approved docs/decision update.
- Keep `content` as the content owner and `learning` as the user-learning-state
  owner.
- Keep subscription/paywall checks out of content models. Topic owns only the `demo/free/paid` access classification; entitlement decisions stay behind subscriptions policy.
- Do not use Django signals for core business logic.
- Do not add Repository/UnitOfWork/EventBus/CommandBus layers or generic utility
  packages without a concrete approved need.
- Redis is cache in MVP. Celery, Kafka, RabbitMQ, Elasticsearch, Kubernetes,
  microservices and new external providers require an explicit decision.

## Implementation rules

- Follow the owning app and layer responsibilities from
  `docs/architecture/target-architecture.md`.
- Keep views thin; put write use cases in services and complex reads in
  selectors.
- Put serializers at the transport boundary, not core business workflows.
- Put transaction boundaries in services.
- Use parameterized ORM/query APIs; never hardcode secrets.
- Keep timestamps timezone-aware/UTC and IDs on the BigAutoField direction.
- Commit migrations with model changes; never rewrite applied migration history.
- Keep API errors in the documented envelope and update OpenAPI for public API
  changes.
- Log technical context without passwords, JWTs, refresh cookies, Telegram
  secrets or raw sensitive payloads.

## Testing and verification

Every behavior change must include or update tests. At minimum cover happy path,
permissions, validation/errors and important boundary/concurrency cases required
by the spec.

After implementation, run the narrowest relevant checks first, then the project
checks that exist:

```text
uv run ruff format --check .
uv run ruff check .
uv run pytest
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
```

If a command cannot run because the project skeleton/tooling is not present,
report that fact instead of claiming success. Report exact commands and results.

## Scope and escalation

The agent may decide local implementation details that preserve the approved
contract: names, function decomposition, queryset optimization and test fixture
shape. It must escalate:

- product behavior not present in the spec;
- any `TBD` decision;
- new cross-domain dependency;
- auth/permission/paywall/security change;
- public API or migration compatibility change;
- new dependency or infrastructure component;
- a spec/ADR/code conflict.

When blocked, return a concise `BLOCKED` report with evidence, affected scope
and the exact decision required. Do not create speculative code to hide the
blocker.

## Documentation updates

If implementation reveals an architecture/spec mismatch, do not silently rewrite
the docs. Report it first. After an approved decision, update the relevant
architecture document/spec and keep the change focused. Do not create dozens of
ADRs or duplicate `medcore-docs` content.
