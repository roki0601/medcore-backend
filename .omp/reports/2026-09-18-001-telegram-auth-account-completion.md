# Completion report: feature 001 Telegram auth and user account

- Feature: `001-telegram-auth-account`
- Branch: `feature/001-telegram-auth-account`
- Worktree: `/home/roki/dev/medcore/medcore-backend` (clean)
- Date: 2026-09-18
- Decision record: `.omp/decisions/2026-09-18-001-telegram-auth-account-quorum.md`
- Tasks: `specs/001-telegram-auth-account/tasks.md` (T001–T032 complete)
- Status: `VERIFIED` for implementation and validation; PR open, human review/merge pending
- Commits: `9ca96cc`, `23b25b7`
- PR: https://github.com/roki0601/medcore-backend/pull/2

## Reviewer verdicts (from the accepted decision record)

| Role | Model | Verdict |
|---|---|---|
| Qwen `spec-reviewer` | `ufanet-local/Qwen3-Coder-Next-NVFP4` | `READY` after round 3, no substantive dissent |
| Luna `watchdog` | `openai-codex/gpt-5.6-luna:high` | `READY` after round 3, no source conflict |
| DeepSeek `architect` | `openrouter/deepseek/deepseek-v4.1-flash:max` | `READY`, conditional on the record plus the feature-contract amendment, both present |

No quorum or spec review was re-run in this session; the record above is the
authority for the implementation contract.

## Delivered scope

- `apps/users/models.py` — username NFKC/trim/lower canonicalization with 3–30
  character and alphabet validators, `RefreshSession`, `TelegramLoginReplay`,
  case-insensitive and non-blank username constraints preserved from `0001`.
- `apps/users/migrations/0002_alter_user_username_telegramloginreplay_and_more.py`
  — forward-only migration: username length change, replay ledger, refresh
  session table and indexes. `0001_initial` is untouched.
- `apps/users/services.py` — legacy Login Widget HMAC verification with the
  sorted `key=value` data-check string and `SHA256(bot token)` key, 86400-second
  freshness plus 60-second future skew, atomic replay-digest consume, canonical
  `telegram_id` lookup/create with unique-race retry, application-username
  generation, token issuance, refresh validation under row lock, revocation,
  username update and transactional account deletion.
- `apps/users/authentication.py`, `apps/users/throttles.py`,
  `apps/users/schema.py` — Bearer authentication with issuer/audience/type,
  active-user and `auth_version` checks; scoped Redis-backed throttles; the
  `bearerAuth` OpenAPI scheme.
- `apps/users/serializers.py`, `apps/users/views.py`, `apps/users/urls.py` —
  request/response boundary and the `csrf`, `telegram`, `token/refresh`,
  `logout`, `logout-all`, `me` endpoints with CSRF protection where the contract
  requires it and OpenAPI metadata on every route.
- `apps/common/exceptions.py`, `apps/common/views.py`, `apps/common/urls.py` —
  the `{code, detail, fields}` envelope, the `CSRF_FAILED` view and the CSRF
  bootstrap endpoint.
- `config/settings/{base,local,production}.py`, `config/urls.py`,
  `.env.example` — SimpleJWT baseline, cookie policy, throttle rates, CORS/CSRF
  origins, schema/docs exposure policy.
- `specs/001-telegram-auth-account/*` — spec amended to the accepted contract,
  plan, research, data model, API contract, quickstart, tasks.

## Validation (exact commands, final tree)

```text
$ uv run ruff format --check .
110 files already formatted

$ uv run ruff check .
All checks passed!

$ uv run pytest
36 passed in 2.51s

$ uv run python manage.py check
System check identified no issues (0 silenced).

$ uv run python manage.py makemigrations --check --dry-run
No changes detected
```

All five checks passed on the first run of the validation stage; no check had to
be repeated after a fix.

## Quickstart smoke (live PostgreSQL + Redis)

`specs/001-telegram-auth-account/quickstart.md` was executed against
`manage.py runserver` with real PostgreSQL and Redis and a temporary throwaway
client script (deleted afterwards). 36/36 checks passed, covering:

1. CSRF bootstrap and cookie;
2. Telegram login returning access token, `expires_in` 900, `has_telegram`
   without leaking `telegram_id`, and the HttpOnly refresh cookie;
3. Bearer `GET /auth/me/`;
4. refresh returning a new access token with an unchanged refresh cookie;
5. logout returning 204, clearing the cookie, and the revoked session then
   failing refresh with `AUTH_REFRESH_REVOKED`;
6. two sessions revoked together by `logout-all` with `AUTH_REFRESH_REVOKED`;
7. wrong delete confirmation returning `INVALID_REQUEST`, `DELETE` returning
   204, and the stale credential then returning `AUTHENTICATION_REQUIRED`;
8. OpenAPI containing all six auth routes, the `bearerAuth` scheme, the refresh
   cookie plus `X-CSRFToken` parameters, the `me` Bearer requirement, and no
   secret material.

Forward migration evidence: `users.0002` applied to a database that already had
`0001` applied and one existing row (max username length 4) without truncation.
After the smoke, `users_user` contains only the pre-existing row, and
`users_refreshsession` is empty — the deleted account's sessions were removed by
the revoke-then-delete transaction and the `ON DELETE CASCADE` foreign key. Four
`users_telegramloginreplay` rows remain, which is the documented MVP retention
behavior.

## Test-suite changes made in this session

The feature tests were already authored and passing. Two plan-required
assertions were missing from the artifacts and were added:

- `apps/users/tests/test_services.py::test_auth_paths_never_log_payload_or_token_secrets`
  — T009's "safe logging expectations": fails if the bot token, payload hash or
  either JWT ever reaches a log record.
- `apps/users/tests/test_api.py::test_concurrent_first_logins_over_http_share_one_user`
  — T010's API-level concurrent first login: both racing requests must return
  200 for the same User with two refresh sessions.

Non-vacuousness was proven for the concurrency tests: with the unique-race retry
loop temporarily reduced to a single attempt, both the service-level and the new
API-level race test failed with `RuntimeError: Telegram authentication retry
exhausted`; the source was restored and byte-compared afterwards.

## Unresolved risks and observations

- Replay-ledger growth has no MVP cleanup; any future cleanup must preserve the
  unique-digest replay invariant (accepted residual risk in the decision record).
- A fresh verified login after deletion intentionally creates a new empty
  account; no data is restored.
- Spec 003 must implement the `ON DELETE CASCADE` User foreign keys before its
  learning-owned models ship; `users` does not import `learning`.
- Production requires `JWT_SIGNING_KEY`, `TELEGRAM_BOT_TOKEN`, allowed hosts,
  CORS/CSRF trusted origins and shared Redis throttling; the production settings
  module fails closed when the secrets are absent.
- API timestamps are stored as UTC but rendered in the project `TIME_ZONE`
  (`Asia/Yekaterinburg`, `+05:00` offset). The instant is correct and
  timezone-aware; only the offset representation differs from the `Z` example in
  the API contract. Changing the rendering would touch a pre-existing
  project-wide setting outside this feature's contract, so it was left as is and
  is recorded here for a decision if the frontend requires `Z`.
- The working tree is uncommitted; migrations must be committed with the model
  changes.

## Next action

Review PR #2 on `feature/001-telegram-auth-account` and merge it manually before
starting `002-content-catalog-access`.
