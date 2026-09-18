# MedCore project watchdog

This file is advisor-only guidance. It does not replace `AGENTS.md`, accepted
decisions, architecture documents, or feature specifications. The delegated
review and decision protocol is defined in `.omp/AUTONOMOUS_REVIEW.md`.

## Review priorities

- Apply source-of-truth precedence: sibling `medcore-docs` accepted decisions,
  backend architecture, approved feature spec, then existing code/tests.
- Treat every `TBD` as unresolved. Do not let an agent silently choose product,
  auth, permission, paywall, data-model, infrastructure, or API semantics.
- Keep `content` as content owner and `learning` as learning-state owner.
  Subscription and entitlement policy must stay behind the subscriptions boundary.
- Reject Django signals for core business logic and new Celery, Kafka, RabbitMQ,
  Elasticsearch, Kubernetes, microservice, or provider dependencies without an
  accepted decision.
- Reject public API, auth/token, permission, migration, or cross-domain changes
  that are outside the approved spec.
- Require tests for happy path, permissions, validation/errors, and relevant
  boundary/concurrency behavior. A failed check cannot be reported as `DONE`.
- Watch for migration rewrites, weakened tests, leaked secrets, raw sensitive
  payloads in logs, and changes to unrelated user work.

## Orchestration policy

- Keep implementation writers sequential: one Qwen worker at a time.
- Use Luna for planning, decomposition, coordination, and ordinary review.
- Escalate architecture, security, auth, subscriptions/paywall, transactions,
  concurrency, destructive migrations, repeated failures, and final high-risk
  review to the DeepSeek roles configured in `.omp/config.yml`.
- Use the project state machine in `PROJECT_STATE.md`; do not skip readiness or
  mark a high-risk feature complete without the full delegated quorum, written
  decision records, and final validation.
- Preserve existing untracked user changes, especially the current feature plan.

## Required validation

Before a feature is considered verified, run the project commands from
`AGENTS.md`, including Ruff, pytest, Django checks, and the migration check.
