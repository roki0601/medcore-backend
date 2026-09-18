# AGENTS.md

## Project role

`medcore-backend` is the Django/DRF backend of MedCore. The backend foundation
already exists and product features are implemented incrementally from approved
specs. Product and architecture decisions are documented; coding agents
implement approved specs and do not invent the system design while coding. For
unattended OMP runs, the owner may delegate spec approval and evidence-backed
blocker resolution to the unanimous quorum described in
`.omp/AUTONOMOUS_REVIEW.md`.

## Source of truth

Use this precedence:

1. Explicit accepted decisions in the sibling `medcore-docs` repository,
   especially `decisions/0004-mvp-decision-register.md` and newer decisions.
2. Backend-specific architecture and conventions in
   `docs/architecture/` (these documents must conform to accepted decisions).
3. The relevant approved implementation-ready feature spec, together with any
   applicable decision record from `.omp/decisions/`; a feature spec may refine
   an implementation contract but cannot silently override architecture or an
   accepted decision.
4. Existing code and tests, once they exist.

`TBD` means unresolved. It is not permission to choose a product or architecture
decision silently. During an unattended OMP run, send the exact blocker through
the multi-model deliberation in `.omp/AUTONOMOUS_REVIEW.md`; resolve it only
with source-backed unanimous agreement and a decision record. If code, spec and
an accepted decision conflict and the sources cannot be reconciled, record the
conflict and stop the affected change.

## Before implementation

The agent must read:

1. this file;
2. relevant `docs/architecture/*` documents;
3. the sibling `medcore-docs/ai/context.md`, `AGENTS.md`, product context and
   accepted decision register;
4. all related ADRs/decision documents, including newer overrides;
5. the complete relevant feature spec and its owner approval or unanimous
   delegated-review record;
6. existing code/tests in the owning app.

The agent must identify the owning Django app, affected entities, dependency
direction, API contract, risks and validation commands before editing.

## Architecture guardrails

- `docs/architecture/` is the backend architecture source of truth.
- Do not independently change architectural style, app ownership, domain
  boundaries, auth/token semantics, permissions, public API, data model or
  infrastructure choices. Those choices may advance during an unattended OMP
  run only when the full delegated quorum resolves the question from
  authoritative project evidence and records the decision.
- Do not expand a task because a broader refactor seems cleaner.
- Do not make optional content required, close a `TBD`, or add a new domain app
  without an approved docs/decision update or a source-backed unanimous
  delegated decision record.
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
shape. For a broader blocker, the unattended OMP manager must first run the
documented multi-model deliberation and write a decision record. The same gate
applies to product behavior not explicit in the spec, `TBD`, new cross-domain
dependencies, auth/permission/paywall/security changes, public API or
migration compatibility changes, new dependencies/infrastructure, and
spec/ADR/code conflicts. A model may derive a resolution from evidence but may
not invent a requirement or override an accepted source. If the quorum cannot
reconcile the sources, return `BLOCKED` with evidence and the exact unresolved
conflict.

## Documentation updates

If implementation reveals an architecture/spec mismatch, do not silently rewrite
the canonical docs. During an unattended OMP run, record the evidence-backed
resolution in `.omp/decisions/` before proceeding, then keep any source-doc
update focused and traceable. Do not create dozens of ADRs or duplicate
`medcore-docs` content.

## Project-local OMP orchestration

Project-local OMP settings and agents live under `.omp/`; `PROJECT_STATE.md`
tracks the orchestration state but does not override the source-of-truth rules
above. Use `scripts/ai/omp-project` to activate the project config and Git
guards. OMP agents must preserve user changes, keep implementation writers
sequential, run the delegated quorum before advancing a blocked or draft
feature, record material decisions and final reports under `.omp/`, and stop
only for an irreconcilable source-of-truth conflict or a failed validation that
the retry policy cannot resolve.
