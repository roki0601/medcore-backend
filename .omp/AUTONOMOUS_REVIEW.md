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

The manager builds a worker plan from the dependency graph, not from the number
of task IDs. A worker zone is a coherent ownership boundary with an explicit
scope: stable zone id, exact files or modules, non-goals, dependencies,
parallel group, risk level, targeted checks, and a small test budget. Treat
`[P]` markers in `tasks.md` only as candidates; verify file ownership and
dependencies before parallelizing.

Choose the smallest safe number of workers dynamically:

1. use one worker when the feature is one coherent zone;
2. use multiple workers only when their writable files, migrations, fixtures,
   contracts, and dependency chains are disjoint;
3. give shared foundations, migrations, public contracts, and shared fixtures
   one owner and complete them before dependent zones;
4. dispatch independent zones from the same parallel group together, while
   keeping overlapping zones sequential;
5. choose `N = min(4, independent zones, available session capacity)`. Lower
   `N` to one when shared mutable state, an unresolved contract, or endpoint
   saturation makes parallel work unsafe. A worker must report a dependency
   instead of editing another zone's files;
6. if a feature has more zones than the cap, process them in dependency-aware
   batches rather than creating a worker for every tiny task.

Every worker receives a compact context packet: base commit, zone ownership,
relevant paths/line ranges, invariants, dependency edges, and exact targeted
commands. Do not copy the manager transcript or unrelated repository context
into every worker. The implementation worker completes its coherent zone and
tests before validation; it must not run Ruff or pytest after every file, edit,
or small refactor. Validation is intentionally batched:

1. finish the task's implementation and tests;
2. run only the zone's relevant formatter/linter/test checks once;
3. fix failures locally, rerunning only the failed check while converging;
4. return the evidence packet; the manager runs the project-wide checks once
   after all zones are integrated, not once per worker.

Do not add a test merely because a line, serializer field echo, or transparent
wrapper exists. For a non-trivial changed contract, cover the applicable happy
path, distinct business invariant, permission or security boundary,
validation/error contract, important boundary/concurrency case, and regression.
Prefer parametrized cases for a behavior matrix and do not duplicate service
and API tests when the API only forwards the same behavior. The worker reports
the test rationale and the number of new tests.

After the last implementation zone, read-only review and smoke preparation may
run in parallel. Use one review pass per applicable risk axis. Create one fixes
worker for all actionable BLOCKER/HIGH findings (and an approved contract-
critical MEDIUM finding), not one worker per finding. Low/info findings remain
in the report unless they block the contract. Run full Ruff, full pytest,
Django checks, migration checks, and live smoke once at the delivery boundary;
rerun only checks affected by a fix before that boundary.

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
action. It also includes the planned/actual worker count, zone start/end times,
targeted-check and final-check durations, critical path, test count/rationale,
and integration waits. It must not contain credentials, JWTs, cookies, Telegram
secrets, or raw sensitive payloads.

## Delivery boundary

The manager is allowed to perform the mechanical delivery sequence after the
implementation and checks are complete: commit intended files, push the
feature-style branch, and create or update a GitHub PR whose body contains the
implementation summary and evidence. Git guards continue to block direct or
force pushes to protected branches, merge/auto-merge, destructive working-tree
operations, and staged secrets. Human review and merge remain outside the
manager's authority.
