# Implementation Plan: Learning state, flashcard review and quizzes

**Branch**: `feature/003-learning-state`
**Date**: 2026-09-19
**Spec**: [spec.md](./spec.md)
**Decision record**: [delegated review](../../.omp/decisions/2026-09-19-003-learning-state-review.md)
**Supporting artifacts**: [research.md](./research.md), [data-model.md](./data-model.md),
[contracts/learning-api.md](./contracts/learning-api.md), [quickstart.md](./quickstart.md)

## Summary

Deliver the personal learning state of MedCore. `apps.learning` stops being a
skeleton and gains four models — `UserTopicProgress`, `UserTopicBlockProgress`,
`FlashcardReview`, `QuizAttempt` — their first migration, the synchronous use
cases (open/mark learned a topic, complete a theory block, review a flashcard,
start/save/submit a quiz attempt), the learner-facing REST surface under
`/api/v1/`, and the access/ownership/throttling contract that keeps learning state
authenticated and user-owned. Every route re-checks the published Topic and the
`content` access decision, so `paid` topics stay denied until the subscriptions
feature supplies the entitlement source, and no anonymous request can create
learning state.

## Technical Context

**Language/Version**: Python 3.12
**Framework**: Django + Django REST Framework
**Storage**: PostgreSQL (learning tables, JSON attempt state); Redis only for
shared DRF throttle counters
**Testing**: pytest, pytest-django, DRF `APIClient`, live PostgreSQL,
`TransactionTestCase` for the concurrency cases
**API**: REST/JSON under `/api/v1/`, drf-spectacular OpenAPI
**Pagination**: DRF page-number, default 20, maximum 100
**Throttles**: `learning_read` 120/min, `learning_progress` 60/min,
`learning_review` 60/min, `learning_attempt` 60/min
**New dependency**: none
**Constraints**: no signals, no Celery/queue, no repository layer, no
subscription-model reads, no content authoring from `learning`, no correctness
leak before submit, forward-only migrations

## Constitution Check

| Gate | Result | Evidence |
|---|---|---|
| Source-of-truth precedence | PASS | The decision record resolves every gap from ADR 0004/0006/0007/0008, `docs/architecture` and the accepted 001/002/004 contracts; the unresolved product parameters (the pass threshold and score-based auto-completion) are explicitly deferred, not invented. |
| Domain ownership | PASS | `learning` owns progress, reviews and attempts; content entities stay owned by `content`; entitlement stays behind `subscriptions.policy`. |
| Dependency direction | PASS | `learning → users`, `learning → content`; the access decision is consumed through `apps.content.access`; no reverse import, no `learning → subscriptions` import. |
| Contract-first API | PASS | `contracts/learning-api.md` fixes every route, payload, status and error before coding. |
| Security boundary | PASS | `IsAuthenticated` on every route, per-request Topic access re-check, ownership with 404 hiding, no correctness in active payloads, throttled writes, secret-safe logs. |
| Data/migration safety | PASS | One additive `0001_initial` migration; unique/partial-unique/check constraints as the race backstop; the cascade matrix is documented in `data-model.md`. |
| MVP simplicity | PASS | Django ORM, synchronous services, derived values instead of stored aggregates, no new dependency or infrastructure. |
| Test evidence | PASS | Tests cover model constraints and the cascade matrix, the progress boundary, the schedule matrix, the scoring matrix, the access/ownership matrix, the attempt lifecycle, and the concurrency invariants. |

## Design decisions

1. **Theory unit is the Topic's published `ContentBlock`** — `UserTopicBlockProgress`
   with `block CASCADE` and no stored topic column (the topic is derived from the
   block, so a content re-parenting cannot go stale), the route
   `POST /api/v1/topics/{topic_id}/blocks/{block_id}/complete/` with a 404 for a
   mismatched pair. Derived `theory_percent = ROUND_HALF_UP(100 × completed/total)`,
   `0` for zero blocks.
2. **Progress transitions** — the first action creates `status=learning`;
   `PATCH {"status": "learned"}` is the only path to `learned` and never regresses;
   `GET` never writes. Score-based auto-completion is deferred (owner decision on
   the threshold).
3. **Flashcard schedule** — settings-driven `LEARNING_FLASHCARD_INTERVALS`
   (default `(1, 3, 7, 14, 30)`); `know` advances one interval, `repeat` resets to
   the first; one current row per user/card; `review-due` returns existing rows
   with `next_review_at <= now` on published, accessible topics.
4. **Attempt state** — `answers_state` (answer IDs only), `question_ids` (frozen
   at start), `results` (null while active). The wire contract exposes
   `selected_answer_ids`, `question_ids`, `questions` and `results`; no
   correctness before submit.
5. **Grading** — `max(0, (correct_selected - incorrect_selected) /
   correct_answer_count)` with `Fraction` arithmetic, unanswered = 0, mean over
   the frozen question set, one `ROUND_HALF_UP` rounding; the result is persisted
   at submit and a submitted attempt is immutable. No pass threshold and no
   `passed` flag: register item 65 forbids introducing a global pass percentage,
   so the threshold is an open owner decision (post-analysis correction 1).
6. **One active attempt** — partial unique constraint plus a locked read in the
   start service; 200 for an existing active attempt, 201 for a new one, 409
   `ACTIVE_ATTEMPT_EXISTS` for the racing loser, 409 `ATTEMPT_ALREADY_SUBMITTED`
   for the submit loser.
7. **Best score** — derived `Max` over the user's submitted attempts, exposed as
   `best_score_percent` on quiz detail and the topic quiz list.
8. **Access and ownership** — published Topic plus `evaluate_topic_access` on
   every route; 404 for missing/unpublished/another user's object, 403
   `TOPIC_ENTITLEMENT_REQUIRED` for a paid denial; `IsAuthenticated` rejects the
   integration principal.
9. **Errors** — reuse the shared `{code, detail, fields}` envelope; `APIError`
   with explicit codes for 401/403/404/409/422.
10. **Package layout** — `progress/`, `flashcards/`, `quizzes/` sub-packages with
    disjoint services/selectors/serializers/views, an app-level `services.py` for
    the shared progress-row primitives, `scheduling.py`/`scoring.py`/`access.py`
    for the pure and shared helpers, and `serializers.py` for the strict-write
    mixin.

## Project structure

```text
apps/learning/
├── models.py                     # four models + choices
├── services.py                   # shared progress-row primitives
├── scheduling.py                 # flashcard interval rules
├── scoring.py                    # quiz grading
├── access.py                     # published-topic access resolution
├── serializers.py                # strict-write mixin
├── urls.py                       # the eleven learning routes
├── migrations/0001_initial.py
├── progress/
│   ├── services.py               # open / mark learned / complete block
│   ├── selectors.py              # derived snapshot
│   ├── serializers.py
│   └── views.py
├── flashcards/
│   ├── services.py               # review action
│   ├── selectors.py              # topic list, due list, review map
│   ├── serializers.py
│   └── views.py
├── quizzes/
│   ├── services.py               # start / save / submit
│   ├── selectors.py              # quiz reads, best score, frozen questions
│   ├── serializers.py
│   └── views.py
└── tests/
    ├── conftest.py
    ├── test_models.py
    ├── test_scheduling.py
    ├── test_scoring.py
    ├── test_progress_api.py
    ├── test_flashcards_api.py
    └── test_quizzes_api.py

config/settings/base.py           # LEARNING_* settings, learning throttle scopes
config/urls.py                    # include apps.learning.urls
```

## Implementation order and zones

Zones are ownership boundaries, not task IDs. Each zone owns its files
exclusively; a worker that needs another zone's file reports the dependency
instead of editing it.

| Zone | Owner scope (writable files) | Depends on | Parallel group |
|---|---|---|---|
| `Z1-foundation` | `apps/learning/models.py`, `migrations/0001_initial.py`, `services.py`, `scheduling.py`, `scoring.py`, `access.py`, `serializers.py`, `urls.py`, the three sub-package placeholders (`progress/`, `flashcards/`, `quizzes/`: `__init__.py` and an empty `urls.py`), `tests/conftest.py`, `tests/test_models.py`, `tests/test_scheduling.py`, `tests/test_scoring.py`, `config/settings/base.py`, `config/urls.py` | — | 1 (blocking) |
| `Z2-progress` | `apps/learning/progress/{urls,selectors,services,serializers,views}.py`, `tests/test_progress_api.py` | `Z1-foundation` | 2 |
| `Z3-flashcards` | `apps/learning/flashcards/{urls,selectors,services,serializers,views}.py`, `tests/test_flashcards_api.py` | `Z1-foundation` | 2 |
| `Z4-quizzes` | `apps/learning/quizzes/{urls,selectors,services,serializers,views}.py`, `tests/test_quizzes_api.py` | `Z1-foundation` | 2 |

`Z1-foundation` creates the three sub-package placeholders and the app-level URL
aggregation, then hands each sub-package to its zone: the placeholders exist so the
foundation checkpoint (`manage.py check`, migration apply, helper imports) is
reachable before the feature zones exist, and each zone fills only its own
`urls.py` and modules. Wave 2 runs `Z2`, `Z3` and `Z4` together because their
writable files are disjoint and their shared contract is fixed by this plan.

## Risks and mitigations

- **Threshold deferral** — accepted register behavior with a TBD threshold
  (item 65: no global pass percentage; items 67-68: auto-completion with a TBD
  threshold); recorded in the spec and decision record, surfaced to the owner as
  an open decision. No silent scope shrink.
- **`is_correct` edits during an active attempt** — accepted by the escalation
  review; the frozen question set plus the persisted result keep submitted
  attempts reproducible.
- **Quiz detail vs active attempt question sets** — the attempt payload is
  authoritative for a resumed attempt; documented in the contract.
- **Cascade-only cross-domain deletion** — no `content`/`users` import of
  `learning`; the FK matrix is proven by tests.
- **`paid` topics** — unreachable until the subscriptions feature ships the
  entitlement source; the deny path is exercised through the policy seam.
- **`GET /progress/` must not write** — asserted by a test that counts rows before
  and after the request.

## Complexity Tracking

No constitution violations. No Repository/UnitOfWork/EventBus layer, queue,
provider infrastructure or unrelated refactor is introduced. The only structural
change beyond the feature itself is turning `apps/learning` into a package with
three sub-domains, which keeps the parallel implementation zones disjoint and
follows the "large apps may become packages" guidance in
`docs/architecture/target-architecture.md`.
