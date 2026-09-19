# Project-local OMP setup

This directory is the MedCore-only OMP configuration. It intentionally does
not change `~/.omp`, credentials, neighboring repositories, or system settings.
The project wrapper routes all ordinary manager, implementation and review roles
to `openrouter/deepseek/deepseek-v4.1-flash`; Luna remains an explicit
escalation-only watchdog.

Use the wrapper from the repository root:

```bash
./scripts/ai/omp-project --model @plan --approval-mode yolo
```

Do not add `--advisor`: it makes Luna review every turn. The manager invokes the
Luna Watchdog only for an explicit escalation. The project agents are discovered
from `.omp/agents`; the recommended roles are:

- `manager` — dependency-aware orchestration, dynamic zone planning, and
  state-machine control;
- `implementer` — one focused DeepSeek implementation zone;
- `architect` — optional DeepSeek read-only architecture/risk analysis;
- `senior-reviewer` — optional DeepSeek read-only high-risk/final review;
- `watchdog` — Luna read-only escalation check;
- `spec-reviewer` — optional DeepSeek read-only specification/readiness check.

For unattended work, start the manager with approval mode:

```bash
./scripts/ai/omp-project --model @plan --approval-mode yolo
```

The manager chooses the worker count from the dependency graph: one worker for
one coherent zone, or up to four workers in parallel for disjoint zones. Shared
foundations, migrations, contracts, fixtures, and overlapping files stay
sequential. Each worker receives only a compact context packet and runs only
zone-targeted checks. The manager owns one project-wide validation and delivery
pass after integration and records the worker timings/critical path. Tests are
behavior-focused; trivial field echo,
transparent wrappers, and duplicate service/API coverage do not justify new
tests. The project wrapper passes `--no-title`: session-title generation is
non-functional overhead and must not add a timeout before every manager or
worker session. No project-local Qwen/Ufanet provider is registered.

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

Before starting a new feature, the manager must check and fast-forward only
`medcore-docs` and `medcore-backend` before entering `SPEC_REVIEW`, creating a
feature branch, or delegating implementation:

```bash
cd /home/roki/dev/medcore
git -C medcore-docs pull --ff-only
git -C medcore-backend pull --ff-only
```

`medcore-frontend` is owned by another model and is outside backend OMP scope.
Do not inspect it or run `git status`, `git pull`, checkout, branch, worktree,
tests, or modifications there. Run `git status --short --branch` first only in
the two in-scope repositories. A dirty worktree, missing upstream, or diverged
branch is a blocker to report to the owner. Do not bypass it with automatic
stash, reset, checkout, merge, or rebase. Record the resulting branches and
commit HEADs in the task report. Generic three-repository wording in sibling
docs instructions is contextual and must not be executed by backend OMP.

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
with mode `0600`. Messages use Telegram `MarkdownV2`: the report has compact
headings, escaped dynamic values, readable bullets and disabled link previews.
The top-level process sends one final manager report once per session: an
explicit final status is sent when the manager produces it, and
`session_shutdown` is the single fallback boundary. If the session ends without
a confirmed manager result, it sends one explicit warning `⚠️ OMP: итог не
подтверждён`; a fake successful completion or the old `Итоговый текст
отсутствует` fallback is never sent. Successful child
`<task-result>` events stay silent; only actionable child blockers or
`NEEDS_HUMAN_REVIEW` notifications are forwarded, once per result. Every
notification identifies the agent, role and flow. Rotate any token that was
pasted into chat before storing a fresh one locally.

## Agent report language

All owner-facing reports from the manager and child agents — including
completion reports, blocker notices, review verdicts, decision summaries and
Telegram mini-reports — must be written in Russian. Keep code identifiers,
machine-readable status values, URLs, commands and short source quotations in
their original form when changing them would reduce precision.
