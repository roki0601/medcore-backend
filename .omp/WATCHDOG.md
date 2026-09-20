# MedCore backend escalation watchdog

This is emergency review guidance only. Normal design review and final review
are handled by the bounded Gemini roles described in
`.omp/AUTONOMOUS_REVIEW.md`.

## Escalation priorities

Apply source precedence:

1. accepted sibling `medcore-docs` decisions;
2. approved backend spec;
3. backend architecture and `AGENTS.md`;
4. selected `backend-features` brief;
5. current code/tests.

Treat every unresolved `TBD` as unresolved.

Escalation should focus only on the concrete incident:

- source conflict;
- security/auth/permission risk;
- destructive migration/data-loss risk;
- transaction/concurrency failure;
- repeated deterministic failure after two concrete fixes.

Reject new infrastructure or provider dependencies without an accepted feature
contract. Keep content, learning and subscriptions ownership boundaries intact.

## Orchestration

- Grok owns ordinary design and implementation.
- Gemini owns the two normal bounded review gates.
- Claude watchdog is detached and invoked only on an objective escalation.
- Do not create review chains or quorum loops.
- One compact escalation packet, one verdict.

## Required final validation

Normal completion still requires:

```text
uv run ruff format --check .
uv run ruff check .
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run pytest --create-db
```

A failed/skipped check cannot be reported as VERIFIED.
