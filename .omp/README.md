# Project-local OMP setup

This directory is the MedCore-only OMP configuration. It intentionally does
not change `~/.omp`, credentials, neighboring repositories, or system settings.
The project wrapper keeps the existing local Qwen endpoint available for tiny
helper/title jobs and routes the manager and implementation roles to
`openrouter/deepseek/deepseek-v4.1-flash`.

Use the wrapper from the repository root:

```bash
./scripts/ai/omp-project --model @plan --approval-mode yolo
```

Do not add `--advisor`: it makes Luna review every turn. The manager invokes the
Luna Watchdog only for an explicit escalation. The project agents are discovered
from `.omp/agents`; the recommended roles are:

- `manager` — sequential orchestration and state-machine control;
- `implementer` — one focused DeepSeek implementation task;
- `architect` — optional DeepSeek read-only architecture/risk analysis;
- `senior-reviewer` — optional DeepSeek read-only high-risk/final review;
- `watchdog` — Luna read-only escalation check;
- `spec-reviewer` — optional DeepSeek read-only specification/readiness check.

For unattended work, start the manager with approval mode:

```bash
./scripts/ai/omp-project --model @plan --approval-mode yolo
```

The manager writes material decisions and any Luna escalation to
`.omp/decisions/`, then writes the final task report to `.omp/reports/`. A
disagreement with an accepted source remains a recorded blocker rather than an
invented answer.

Task isolation is enabled with the automatic backend and patch integration. A
manager can request `isolated: true` for an implementation task; the isolated
workspace is temporary and its patch is applied back to the current worktree.
For a persistent PR, use `omp worktree add` first and run OMP from that
worktree. After validation the manager may commit the intended changes, push
the feature-style branch, and create/update a PR with `gh pr create` or
`gh pr edit`. It must not merge or auto-merge the PR.

The retry policy is issue-level: keep DeepSeek on the task, and invoke Luna only
after the same failure repeats, progress stalls, the primary reports serious
uncertainty, or authoritative sources conflict. Record the trigger, evidence,
Luna's verdict, and the follow-up in `.omp/decisions/`. Only an irreconcilable
source conflict or an unresolvable validation failure marks the task `BLOCKED`.

## New feature repository preflight

Before starting a new feature, the manager must check and fast-forward all three
MedCore repositories before entering `SPEC_REVIEW`, creating a feature branch,
or delegating implementation:

```bash
cd /home/roki/dev/medcore
git -C medcore-docs pull --ff-only
git -C medcore-backend pull --ff-only
git -C medcore-frontend pull --ff-only
```

Run `git status --short --branch` first in each repository. A dirty worktree,
missing upstream, or diverged branch is a blocker to report to the owner. Do
not bypass it with automatic stash, reset, checkout, merge, or rebase. Record
the resulting branches and commit HEADs in the task report.

Git safety guards are active when OMP is started through the wrapper. They block
direct/force pushes outside an explicit feature-style branch, merges, history
rewrites, destructive reset/clean/restore operations, `--no-verify` commits,
and commits that fail the staged-secret check. Index-only
`git restore --staged` is allowed so the manager can correct an explicit
staging set. Feature-branch commits, pushes, and `gh pr create`/`gh pr edit`
remain allowed; merge is still blocked. The guards do not police commands run
in a separate terminal.

## Telegram notifications

The wrapper loads `.omp/extensions/telegram-notifications.mjs`. Notifications
are best-effort and silent unless configured. The extension reads only a
dedicated local file, never the project `.env`, so the bot token is not exposed
to model shell commands:

```bash
./scripts/ai/telegram-notifications-setup
```

The setup script stores `OMP_TELEGRAM_BOT_TOKEN` and
`OMP_TELEGRAM_CHAT_ID` in `${XDG_CONFIG_HOME:-$HOME/.config}/medcore/omp-telegram.env`
with mode `0600`. It sends a Telegram message for explicit blockers and the
final OMP result. Every message identifies the agent, role and flow, and puts
the redacted conclusion under `Мини-отчёт`. When the top-level OMP process
receives a standard `<task-result>` from a child agent, it also sends a separate
mini-report for that child (`id`, role, status/verdict and summary). Rotate any
token that was pasted into chat before storing a fresh one locally.
