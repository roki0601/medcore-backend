# Autonomous review and decision policy

This policy is the project owner's delegation for unattended OMP runs. It
allows the configured models to review a draft, resolve evidence-backed
implementation blockers, and continue without waiting for an interactive user
approval. It does not authorize silent changes to accepted decisions or
architecture.

## Review quorum

The manager must obtain independent reviews from all three roles before moving
past `SPEC_REVIEW` or accepting a decision that resolves a blocker:

1. `spec-reviewer` — Qwen via `@task`: completeness, acceptance criteria,
   boundaries, testability, and implementation readiness.
2. `watchdog` — Luna via `@advisor`: repository policy, state-machine,
   source-of-truth, scope, and security checks.
3. `architect` — DeepSeek via `@architect`: domain ownership, API/auth/
   permission semantics, migrations, transactions, concurrency, and operational
   risk.

The manager's own conclusion does not count as a fourth vote. Every reviewer
reads the authoritative material independently before seeing the other reviews.

## Blocker deliberation

When a reviewer reports a blocker:

1. The manager extracts the exact question and the minimum relevant evidence.
2. All reviewers read the applicable `AGENTS.md`, accepted decisions,
   architecture documents, complete feature spec, related specs, current code,
   and tests.
3. The manager requests an independent proposed resolution from each reviewer.
4. The manager shares the competing findings, asks each reviewer to challenge
   the alternatives, and repeats this for at most three rounds.
5. A blocker is resolved only when all three reviewers converge on the same
   evidence-backed decision and no reviewer leaves a substantive dissent.

Models may derive a decision from project evidence and choose the smallest,
least-risk implementation that preserves the documented contract. They must
not invent a product requirement, override an accepted ADR, weaken a security
invariant, or treat an absent dependency contract as present. An irreconcilable
conflict between authoritative sources remains a hard `BLOCKED` result and is
recorded for later review; the manager must not hide it by guessing.

High risk by itself is not a human gate. Auth, account deletion, permissions,
migrations, and other high-risk changes require the full quorum plus a written
decision record and a successful final DeepSeek review.

## Decision records

Every resolved blocker or material autonomous interpretation is recorded before
the workflow advances:

```text
.omp/decisions/YYYY-MM-DD-<feature>-<short-slug>.md
```

The record must contain:

- the question/blocker and affected workflow state;
- source paths and line references used as evidence;
- each model's initial finding and the deliberation/rebuttal;
- the final decision, rejected alternatives, and residual risk;
- the exact state transition and validation/rollback consequence;
- model roles, model identifiers, and UTC timestamp.

Decision records are an audit trail for this delegated run. They cannot silently
supersede the sibling `medcore-docs` decisions or backend architecture. If the
implementation requires a canonical product-document change, the manager must
record that dependency and stop unless the change is directly supported by the
existing sources.

## Completion reports

Every run that reaches `VERIFIED` or `BLOCKED` writes a final report to:

```text
.omp/reports/<feature>.md
```

The report includes the decision-record links, branch/commit/PR, files changed,
exact checks and results, reviewer verdicts, unresolved risks, and the next
action. It must not contain credentials, JWTs, cookies, Telegram secrets, or raw
sensitive payloads.
