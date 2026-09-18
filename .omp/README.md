# Project-local OMP setup

This directory is the MedCore-only OMP configuration. It intentionally does
not change `~/.omp`, credentials, neighboring repositories, or system settings.
The project wrapper maps the existing `ufanet/Qwen3-Coder-Next-NVFP4` model to
the already-running local corporate endpoint at `127.0.0.1:8055`; the tunnel or
local service must already be available.

Use the wrapper from the repository root:

```bash
./scripts/ai/omp-project --model @plan
```

Add `--advisor` when the Luna Watchdog should review the session. The project
agents are discovered from `.omp/agents`; the recommended roles are:

- `manager` — sequential orchestration and state-machine control;
- `implementer` — one focused Qwen implementation task;
- `architect` — DeepSeek read-only architecture/risk analysis;
- `senior-reviewer` — DeepSeek read-only high-risk/final review;
- `watchdog` — Luna read-only project-policy check;
- `spec-reviewer` — Qwen read-only specification/readiness check.

For unattended work, start the manager with the delegated quorum and approval
mode:

```bash
./scripts/ai/omp-project --model @plan --advisor --approval-mode yolo
```

The manager must obtain Qwen, Luna, and DeepSeek agreement before implementation
and writes material decisions to `.omp/decisions/` and the final task report to
`.omp/reports/`. A disagreement with an accepted source remains a recorded
blocker rather than an invented answer.

Task isolation is enabled with the automatic backend and patch integration. A
manager can request `isolated: true` for an implementation task; the isolated
workspace is temporary and its patch is applied back to the current worktree.
For a persistent PR, use `omp worktree add` first and run OMP from that
worktree.

The retry policy is task-level: first retry with Qwen, second with Luna, third
with DeepSeek, then run the bounded quorum deliberation and record the result.
Only an irreconcilable source conflict or an unresolvable validation failure
marks the task `BLOCKED`. This is deliberately not encoded as provider
failover, which would change model choice for unrelated requests.

Git safety guards are active when OMP is started through the wrapper. They block
direct/force pushes outside an explicit feature-style branch, merges, history
rewrites, destructive reset/clean/restore operations, `--no-verify` commits,
and commits that fail the staged-secret check. They do not police commands run
in a separate terminal.
