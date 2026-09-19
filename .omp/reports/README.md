# Autonomous run reports

The OMP manager writes one final report per feature to this directory after a
run reaches `VERIFIED` or `BLOCKED`. Reports must link the relevant files under
`.omp/decisions/` and include exact commands/results, reviewer verdicts, branch,
commit, PR, unresolved risks, and the next action.

Never include credentials, JWTs, cookies, Telegram secrets, or raw sensitive
payloads.
