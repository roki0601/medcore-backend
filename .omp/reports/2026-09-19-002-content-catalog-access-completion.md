# Completion report: feature 002 content catalog and Topic access

- Feature: `002-content-catalog-access`
- Branch: `feature/002-content-catalog-access` (base `e530c4f` on `main`)
- Worktree: `/home/roki/dev/medcore/medcore-backend`
- Date: 2026-09-19
- Decision record: `.omp/decisions/2026-09-19-002-content-catalog-access-quorum.md`
- Tasks: `specs/002-content-catalog-access/tasks.md` (T001–T028 complete)
- Status: `VERIFIED` for implementation and validation; PR open, human
  review/merge pending
- Commit: `52cae11`
- PR: https://github.com/roki0601/medcore-backend/pull/5
- Spec: `specs/002-content-catalog-access/spec.md` amended to the accepted
  contract (Status: Approved for implementation)

## Preflight evidence

All three repositories were clean and fast-forwarded on `main` before the
feature branch was created:

| Repository | Branch | HEAD |
|---|---|---|
| `medcore-docs` | `main` | `0b1d51c` |
| `medcore-backend` | `main` | `e530c4f` |
| `medcore-frontend` | `main` | `db3473d` |

`PROJECT_STATE.md` still said PR 2 needed human review before 002; PRs #1–#3 in
`medcore-backend` are `MERGED` and `main` contains the merge commits, so that
gate was already satisfied. `PROJECT_STATE.md` is refreshed by this run.

## Reviewer verdicts

| Role | Model | Verdict |
|---|---|---|
| DeepSeek `spec-reviewer` | `openrouter/deepseek/deepseek-v4.1-flash:high` | `NEEDS_HUMAN_REVIEW`; every listed blocker resolved by the decision record and the governance objection answered by the delegated policy text |
| Luna `watchdog` | `openai-codex/gpt-5.6-luna:high` | `BLOCKED` only on the stale PROJECT_STATE gate (already satisfied) and the Draft/TBD status (resolved by the record + spec amendments); `RESOLVED` on all technical questions as adopted |
| DeepSeek `architect` | `openrouter/deepseek/deepseek-v4.1-flash:max` | `READY` conditional on the decision record and spec amendments, both written |
| DeepSeek `senior-reviewer` | `openrouter/deepseek/deepseek-v4.1-flash` | `APPROVE_WITH_NOTES`; no access-control or data-integrity defect; two LOW findings fixed (F1 re-parenting, F2 validation-error translation) |

## Delivered scope

- `apps/content/models.py` — `Subject`, `Section`, `Topic`,
  `ContentBlockType`, `ContentBlock`, `Source` with `TextChoices`, DB
  `CheckConstraint`s, per-model unique slugs and `(parent, position)` uniqueness.
- `apps/content/migrations/0001_initial.py` (depends on `media.0001`) and
  `0002_seed_content_block_types.py` (idempotent seed of markdown/image/callout).
- `apps/content/services.py` — slug generation with deterministic suffix, locked
  deterministic position assignment with re-parent re-assignment, publish
  preconditions and server-assigned `published_at`, Topic deletion, source
  attach/detach, and translation of domain validation into
  `VALIDATION_ERROR`/422.
- `apps/content/selectors.py` — published-only catalog with `has_demo_preview`,
  ordered content blocks, source loading, grouped title search.
- `apps/content/access.py` — ADR 0007 `demo/free/paid` matrix with the
  demo-preview allowance, composing only `subscriptions.policy`.
- `apps/content/serializers.py`, `views.py`, `urls.py` — the seven read
  endpoints with explicit `AllowAny`, scoped throttles and OpenAPI metadata.
- `apps/content/admin.py` — Django Admin CMS gated on staff plus
  `role in {editor, admin}`, service-backed saves and publish-time form checks.
- `apps/content/validators.py` — raw-HTML and unsafe-URL rejection.
- `apps/media/models.py`, `migrations/0001_initial.py`, `admin.py` — the
  metadata-only `MediaFile` FK target; upload/access-url stay in spec 004.
- `apps/subscriptions/policy.py` — the public
  `has_paid_content_entitlement` boundary (deny-by-default until the
  subscriptions feature ships).
- `apps/common/pagination.py`, `config/settings/base.py`, `config/urls.py` —
  page-number pagination 20/100, `catalog`/`content_read`/`search` throttle
  scopes, content routes.
- `apps/content/tests/*`, `apps/subscriptions/tests/test_policy.py` — 54 new
  tests across models, services, selectors, access, API and the seed migration.
- `specs/002-content-catalog-access/*` — amended spec plus plan, research, data
  model, API contract, quickstart and tasks.

## Validation (exact commands, final tree)

```text
$ uv run ruff format --check .
136 files already formatted

$ uv run ruff check .
All checks passed!

$ uv run pytest
92 passed in 3.27s

$ uv run python manage.py check
System check identified no issues (0 silenced).

$ uv run python manage.py makemigrations --check --dry-run
No changes detected
```

## Non-vacuousness evidence

Two mutation runs proved the access-critical assertions fail when the behavior
is broken; both files were restored and byte-compared by md5:

- removing the demo-preview filter and the paid entitlement check → 8 tests
  failed (preview subset, access matrix, API 403/200 seam);
- disabling the re-parent position re-assignment → the new re-parent test failed
  with `CONTENT_CONFLICT`.

## Quickstart smoke (live PostgreSQL + Redis)

`manage.py runserver` against the dev database with the quickstart seed data; a
throwaway client script was used and deleted afterwards. 15/15 checks passed
(and a first, wider 19/19 run before the two review fixes, which touched only
the write path):

1. subjects list 200 and paginated; missing subject 404 `RESOURCE_NOT_FOUND`;
2. section detail 200 with its subject id;
3. topic list contains only the three published topics (draft absent);
4. free topic reports `has_demo_preview: true`;
5. demo content anonymous → 200 with all published blocks, no `storage_key`;
6. anonymous free content → 200 with exactly the preview block;
7. anonymous paid content → 401 `AUTHENTICATION_REQUIRED`;
8. authenticated paid content → 403 `TOPIC_ENTITLEMENT_REQUIRED`;
9. authenticated free content → 200 full body;
10. draft topic/content → 404;
11. search finds the topic; unknown `subject_id` → 422 `INVALID_RELATION`;
12. OpenAPI contains all seven content paths.

Smoke data was removed from the dev database afterwards.

## Unresolved risks and observations

- Until the subscriptions feature ships, `paid` content is authorable but
  unreadable by everyone; the deny path is real and the allow path is proven
  through the policy seam. The subscriptions/paywall feature must be scheduled
  before paid content is served.
- Spec 004 owns media upload/access-url and signed URLs; 002 delivers the FK
  reference only and never exposes a storage key. `MediaFile` rows are unverified
  metadata, not proof that a storage object exists.
- Anonymous free/paid content is state-dependent (200 preview vs 401), so
  clients must read 401 on that endpoint as "no preview available".
- Global per-model slug uniqueness and `(parent, position)` uniqueness are
  recorded narrowings/closures of open items; later changes need a data
  migration, never a rewrite of applied history.
- Django Admin sits outside the REST permission surface; the content role hook
  plus service validation is the control. Direct ORM writes bypass publish
  preconditions (no per-type DB guard), as recorded.
- `MediaFileAdmin` uses standard Django model permissions; the media surface is
  spec 004's.
- AC4 (anonymous never creates learning state) is vacuous in 002 and belongs to
  spec 003; spec 003 must also ship the learning-owned `ON DELETE CASCADE` to
  Topic/Section declared by this feature.

## Next action

Review the PR on `feature/002-content-catalog-access` and merge manually. Do not
merge from the OMP run. `main` was not pushed to.