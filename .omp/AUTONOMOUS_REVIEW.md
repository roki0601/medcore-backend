# Autonomous review and decision policy

This policy is the project owner's delegation for unattended OMP runs. It
allows the configured models to review a draft, resolve evidence-backed
implementation blockers, and continue without waiting for an interactive user
approval. It does not authorize silent changes to accepted decisions or
architecture.

## Normal execution

DeepSeek V4.1 Flash is the primary model for the manager, planning, and
implementation roles (`@plan` and `@task`). The manager follows the project
state machine and source-of-truth rules directly; it does not create a
multi-model quorum for every feature or ordinary coding turn.

The Luna advisor is not attached to the session. Do not start the project
wrapper with `--advisor`: that mode reviews every turn and recreates the
latency/cost problem this policy is intended to avoid. `smol`/`tiny` may remain
on the local Qwen endpoint for lightweight title/helper work, but they are not
implementation or review authorities.

## Implementation and validation cadence

The implementation worker completes one coherent approved task before running
the normal validation suite. It must not run Ruff or pytest after every file,
edit, or small refactor. During implementation it may inspect code and existing
tests, but validation is intentionally batched:

1. finish the task's implementation and tests;
2. run the narrow relevant formatter/linter/test checks once;
3. fix failures locally, rerunning only the failed check while converging;
4. after the task is coherent, run the required project checks once and report
   their exact results.

A first ordinary lint or test failure is not a Luna escalation. The manager
keeps the fix loop local unless the same signature persists after two concrete
attempts or the evidence reveals a deeper contract/problem.

## Luna escalation

The manager invokes the read-only `watchdog` (`@advisor`) only when at least one
objective trigger is present:

1. the same test/check fails with the same signature after two concrete
   attempts;
2. two attempted fixes produce no new evidence or the agent starts repeating
   the same investigation;
3. the agent reports serious uncertainty or a blocker;
4. accepted decisions, architecture, and the feature spec disagree;
5. a security/auth/permission/migration/transaction/concurrency or destructive
   change needs a second opinion before proceeding.

One escalation receives a compact packet: symptom, attempts, exact evidence,
the decision needed, and the relevant paths. Luna stays read-only and returns
`RESOLVED` with a source-backed recommendation or `BLOCKED` with the exact
unresolved conflict. The manager must not invoke Luna for routine progress,
ordinary review, every turn, or the first test/lint failure. Do not repeat the
same escalation without new evidence; at most two bounded challenge rounds are
allowed for one incident.

## Blocker deliberation

When the primary run reports a blocker:

1. The manager extracts the exact question and the minimum relevant evidence.
2. The manager reads the applicable `AGENTS.md`, accepted decisions,
   architecture documents, complete feature spec, related specs, current code,
   and tests.
3. If an escalation trigger is present, the manager sends the compact packet to
   Luna and asks for one independent proposed resolution.
4. The manager applies only a source-backed resolution. If the evidence still
   conflicts after at most two bounded rounds, the state is `BLOCKED`.

Models may derive a decision from project evidence and choose the smallest,
least-risk implementation that preserves the documented contract. They must
not invent a product requirement, override an accepted ADR, weaken a security
invariant, or treat an absent dependency contract as present. An irreconcilable
conflict between authoritative sources remains a hard `BLOCKED` result and is
recorded for later review; the manager must not hide it by guessing.

High risk by itself is not a human gate. High-risk work gets a Luna escalation
when one of the objective triggers above is present; it does not get a
permanent advisor or an automatic full quorum.

## Decision records

Every Luna escalation, resolved blocker, or material autonomous interpretation
is recorded before the workflow advances:

```text
.omp/decisions/YYYY-MM-DD-<feature>-<short-slug>.md
```

The record must contain:

- the question/blocker and affected workflow state;
- source paths and line references used as evidence;
- DeepSeek's finding, Luna's escalation verdict when invoked, and the
  deliberation/rebuttal;
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

## Delivery boundary

The manager is allowed to perform the mechanical delivery sequence after the
implementation and checks are complete: commit intended files, push the
feature-style branch, and create or update a GitHub PR whose body contains the
implementation summary and evidence. Git guards continue to block direct or
force pushes to protected branches, merge/auto-merge, destructive working-tree
operations, and staged secrets. Human review and merge remain outside the
manager's authority.
