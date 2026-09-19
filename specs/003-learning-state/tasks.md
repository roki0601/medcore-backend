# Tasks: Learning state, flashcard review and quizzes

**Input**: design documents from `specs/003-learning-state/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`,
`contracts/learning-api.md`, `quickstart.md`, and the accepted delegated review in
`.omp/decisions/2026-09-19-003-learning-state-review.md` (including its
post-analysis corrections).

**Tests**: required by the project rules and the spec's test scenarios. Each zone
writes its own test file; the fixtures live in the shared `tests/conftest.py`
owned by `Z1-foundation`.

**Zones**: `Z1-foundation` is a blocking prerequisite for the three feature
zones. `Z2-progress`, `Z3-flashcards` and `Z4-quizzes` own disjoint files and run
in one parallel group after `Z1`. A worker that needs a file outside its zone
reports the dependency instead of editing it. The exact route/class-name contract
is in `contracts/learning-api.md` ("Routes, names and view classes").

## Phase 1: Foundation (`Z1-foundation`, blocking)

**Goal**: schema, migration, shared helpers, transport primitives, URL
aggregation and test fixtures that every feature zone consumes.

- [X] T001 [Z1] Add `LEARNING_FLASHCARD_INTERVALS = (1, 3, 7, 14, 30)` and the
  `learning_read` 120/min, `learning_progress` 60/min, `learning_review` 60/min,
  `learning_attempt` 60/min throttle scopes in `config/settings/base.py` (no new
  environment variable; the values are project defaults). No pass-threshold
  setting is introduced (decision record, post-analysis correction 1).
- [X] T002 [Z1] Add `UserTopicProgress`, `UserTopicBlockProgress`,
  `FlashcardReview`, `QuizAttempt` with the fields, choices, constraints and
  `on_delete=CASCADE` FKs documented in `data-model.md` to
  `apps/learning/models.py`, then generate
  `apps/learning/migrations/0001_initial.py` with `makemigrations learning`.
  `UserTopicBlockProgress` has **no** `topic` column (the topic is derived from
  the block) and `QuizAttempt` has **no** `passed` column.
- [X] T003 [Z1] Add the shared helpers: `apps/learning/scheduling.py`
  (the `index_of`-based advance/reset rules driven by the setting),
  `apps/learning/scoring.py` (`Fraction`-based per-question and total grading with
  a single `ROUND_HALF_UP` rounding; no pass flag),
  `apps/learning/access.py` (published-Topic resolution plus
  `content.access.evaluate_topic_access`, 404/403 mapping, flashcard/quiz
  resolvers), `apps/learning/serializers.py` (the app's strict-write mixin:
  unknown field → 422 `VALIDATION_ERROR`) and `apps/learning/services.py`
  (progress-row lifecycle primitives `ensure_topic_progress` and
  `touch_topic_learning` with savepoint-retry on the unique race; `learned` never
  regresses).
- [X] T004 [Z1] Add `apps/learning/urls.py` (three `include()`s of the sub-package
  URL modules), create the three sub-package placeholders
  (`apps/learning/{progress,flashcards,quizzes}/__init__.py` and a `urls.py` with
  an empty `urlpatterns`), and include the app under `/api/v1/` in
  `config/urls.py`. The feature zones replace their own empty `urls.py` only.
- [X] T005 [Z1] Add `apps/learning/tests/conftest.py` (local cache, JWT signing
  key, `api_client`, `authenticate`, `make_user`, demo/free/paid topic factories,
  published/unpublished block, flashcard and quiz builders) plus
  `tests/test_models.py` (uniqueness, the partial-unique active attempt, the score
  bounds check, the full cascade matrix and no-orphan behaviour),
  `tests/test_scheduling.py` (first `know`, advance, sticky last interval, `repeat`
  reset, settings override) and `tests/test_scoring.py` (single/multiple correct
  answers, partial credit, negative floor, unanswered, empty set, `ROUND_HALF_UP`
  boundaries, and that per-question display rounding does not change the stored
  total). **Targeted check**:
  `uv run pytest apps/learning/tests/test_models.py apps/learning/tests/test_scheduling.py apps/learning/tests/test_scoring.py`.

**Checkpoint**: the migration applies and every shared helper imports; the routes
are not registered yet (the placeholders are empty).

## Phase 2: User Story 1 - theory progress (`Z2-progress`)

**Goal**: an authenticated user completes theory blocks of an accessible Topic,
sees the derived percentage, and can mark the Topic learned manually.

- [X] T006 [Z2] Implement `apps/learning/progress/{urls,selectors,services,serializers,views}.py`:
  the derived snapshot selector (published blocks of the Topic, the user's
  completed rows filtered on `block__topic` and `block__status=published`,
  `ROUND_HALF_UP` percentage, `0` for zero blocks), `open_topic`,
  `complete_topic_block` (topic resolved from the block, mismatched URL topic →
  404, idempotent upsert, progress → `learning`) and `mark_topic_learned` (no
  regression), with `GET`/`PATCH /topics/{id}/progress/` and
  `POST /topics/{id}/blocks/{id}/complete/` registered in the sub-package
  `urls.py`, `IsAuthenticated`, the `learning_read`/`learning_progress` scopes and
  `extend_schema` metadata.
- [X] T007 [Z2] Add `apps/learning/tests/test_progress_api.py`: percentage
  boundary (zero published blocks, partial, complete), first-completion 201 and
  repeat 200, `GET` creating no row (row count asserted), `PATCH` open/learned
  transitions and non-regression, unknown field 422, anonymous 401, another
  topic's block 404, paid topic 403 `TOPIC_ENTITLEMENT_REQUIRED`, unpublished
  topic 404, a block re-parented to another Topic no longer counting for the old
  Topic, and the throttle scope. **Targeted check**:
  `uv run pytest apps/learning/tests/test_progress_api.py`.

## Phase 3: User Story 2 - flashcard review (`Z3-flashcards`)

**Goal**: a user reviews cards with `know`/`repeat`, keeps one current schedule row
per card, and can list what is due.

- [X] T008 [Z3] Implement `apps/learning/flashcards/{urls,selectors,services,serializers,views}.py`:
  the topic list with the user's review state, the detail, the due selector
  (`next_review_at <= now`, published and accessible topics only, ordered by
  `(next_review_at, id)`), `review_flashcard` (atomic, savepoint-retry on the
  unique race, 201/200, and the Topic progress row moved to `learning` in the same
  transaction) and the four routes with `IsAuthenticated`, the
  `learning_read`/`learning_review` scopes, pagination and `extend_schema`
  metadata.
- [X] T009 [Z3] Add `apps/learning/tests/test_flashcards_api.py`: first `know`
  and first `repeat`, the advance/reset matrix through the API, the same row being
  updated (no duplicates), the review action creating the progress row and setting
  it to `learning` (without regressing `learned`), `review` null for a
  never-reviewed card, the due list excluding future and unpublished/inaccessible
  cards, invalid action 422, unknown field 422, anonymous 401 and the
  concurrent-review invariant (`TransactionTestCase`). **Targeted check**:
  `uv run pytest apps/learning/tests/test_flashcards_api.py`.

## Phase 4: User Story 3 - quiz attempts (`Z4-quizzes`)

**Goal**: a user starts, resumes, submits and retakes quizzes; scores are partial,
bounded and reproducible.

- [X] T010 [Z4] Implement `apps/learning/quizzes/{urls,selectors,services,serializers,views}.py`:
  the topic quiz list and quiz detail with `best_score_percent` and questions
  without `is_correct`, `start_attempt` (frozen `question_ids`, progress →
  `learning`, 200/201/409), `save_attempt_answers` (full replacement, ownership,
  frozen-set validation, 422 `INVALID_ANSWER`, 409 on a submitted attempt),
  `submit_attempt` (row lock, grading, persisted `results` and `score_percent`,
  no pass flag, 409 on the concurrent loser) and the five routes with
  `IsAuthenticated`, the `learning_read`/`learning_attempt` scopes, pagination and
  `extend_schema` metadata.
- [X] T011 [Z4] Add `apps/learning/tests/test_quizzes_api.py`: start 201 then 200
  with the same attempt, resume after PATCH, invalid/foreign answer IDs 422,
  submitted-attempt PATCH/submit 409, the scoring matrix through the API (single
  and multiple correct answers, negative floor, unanswered, rounding), a
  `is_correct` flip after start being reflected at submit, retake creating a second
  attempt without touching the first, `best_score_percent` derivation, the frozen
  question set ignoring a question added after start, no `is_correct` in the quiz
  detail or the active attempt payload, another user's attempt 404, anonymous 401,
  paid 403, unknown/empty-body field 422, throttling, and the concurrent
  start/submit conflicts (`TransactionTestCase`). **Targeted check**:
  `uv run pytest apps/learning/tests/test_quizzes_api.py`.

## Phase 5: Polish and validation (manager)

- [X] T012 Verify the OpenAPI schema exposes all eleven learning paths with their
  methods, permissions and error responses, and that no active-attempt or quiz
  payload contains `is_correct` (a schema/response assertion, not a manual read).
- [X] T013 Run `specs/003-learning-state/quickstart.md` against live PostgreSQL and
  Redis and record the evidence.
- [X] T014 Run the exact `AGENTS.md` project checks and record the command/output
  evidence in the completion report.

## Dependencies and execution order

- `Z1-foundation` blocks `Z2-progress`, `Z3-flashcards` and `Z4-quizzes`.
- `Z2`, `Z3` and `Z4` are one parallel group: their writable files are disjoint
  (`progress/**`, `flashcards/**`, `quizzes/**` and one test file each) and their
  shared contract is fixed by `plan.md`, `data-model.md` and
  `contracts/learning-api.md`.
- Shared files (`models.py`, `services.py`, `scheduling.py`, `scoring.py`,
  `access.py`, `serializers.py`, `urls.py`, `conftest.py`,
  `config/settings/base.py`, `config/urls.py`) have exactly one owner:
  `Z1-foundation`.
- Polish runs after all three zones are integrated; the manager runs the
  project-wide checks once.

## Test budget

| Zone | File | Tests | Why they exist |
|---|---|---:|---|
| Z1 | `test_models.py` | ~9 | DB invariants and the cross-domain cascade contract are the last line of defence for ownership and the one-active-attempt rule. |
| Z1 | `test_scheduling.py` | ~6 | The schedule matrix (first know, advance, sticky last, reset, settings override) is a distinct business invariant. |
| Z1 | `test_scoring.py` | ~11 | Partial scoring, the negative floor, unanswered questions and rounding are the feature's numeric contract. |
| Z2 | `test_progress_api.py` | ~11 | Percentage boundaries, idempotency, transition rules, the permission/access matrix and the re-parenting case. |
| Z3 | `test_flashcards_api.py` | ~10 | Schedule behaviour through the transport, the progress transition, due filtering, ownership and the review race. |
| Z4 | `test_quizzes_api.py` | ~17 | Attempt lifecycle, validation/error contract, scoring through the API, grading policy, no correctness leak, conflicts. |

No test is added for field echo, a transparent wrapper or a duplicated
service/API path; the API tests assert observable behaviour and the service-level
cases are limited to invariants the transport cannot express.

## Implementation strategy

1. Foundation first: schema, migration, shared helpers, fixtures and the URL
   aggregation; the feature zones cannot start before its checkpoint.
2. Dispatch `Z2`, `Z3` and `Z4` together, each with the compact context packet
   (base commit, its writable files, its non-goals, the exact route/class names and
   its targeted check).
3. Integrate in dependency order, then run the review passes, the live smoke and
   the full project checks once.
4. Stop and record `BLOCKED` if a source conflict or migration-compatibility issue
   appears; never weaken a test to pass.