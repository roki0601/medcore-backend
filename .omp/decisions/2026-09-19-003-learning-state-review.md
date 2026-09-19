# Delegated review decision: learning state, flashcard review and quizzes

- Feature: `003-learning-state`
- Workflow state: `SPEC_REVIEW` → `DELIBERATING` → `READY_FOR_PLAN`
- Decision status: accepted for this feature implementation
- Decision time: 2026-09-19T13:23:41Z
- Review roles and model identifiers:
  - DeepSeek manager/spec review (source-backed review performed by the manager):
    `openrouter/deepseek/deepseek-v4.1-flash` (`@plan`)
  - Luna `watchdog` escalation: `openai-codex/gpt-5.6-luna` (thinking level `high`),
    one bounded round

## Question and affected workflow state

`specs/003-learning-state/spec.md` is a Draft, High-risk spec. It cannot advance to
planning until the delegated review closes its internal contradictions and fixes the
implementation contracts the spec explicitly leaves to plan time. The open items were: the
"theory section" entity that the accepted content model does not contain; the exact
`answers_state` shape; the attempt-time content-change and aggregate-deletion policy; the
active-attempt concurrency contract; progress transitions versus the accepted register's
score-based auto-completion; the best-score surface; and the stale `TOPIC_ACCESS_DENIED`
error code.

## Preflight evidence

Two-repository preflight before the feature branch, both worktrees clean and
fast-forward:

| Repository | Branch | HEAD |
|---|---|---|
| `medcore-docs` | `main` | `0b1d51c` |
| `medcore-backend` | `main` | `f30b1e4` |

`medcore-frontend` was not inspected (backend OMP scope). `medcore-backend` `main` was 12
commits behind `origin/main` and was fast-forwarded to `f30b1e4` (feature 004 merge
`003154d`, plus PR 7 and PR 8). Branch `feature/003-learning-state` was created from
`f30b1e4`.

## Authoritative evidence

- `AGENTS.md:15-24,27-32,71-85,107-127` — source precedence, delegated spec approval,
  ownership guardrails, migration and validation rules.
- `.omp/AUTONOMOUS_REVIEW.md:11-14,47-83,85-102` — manager performs the source-backed
  review, at most two bounded escalation rounds, every escalation and material
  interpretation gets a record.
- `specs/003-learning-state/spec.md` (whole file) — scope, business rules, invariants, data
  model, API, permissions, validation, errors, transactions, concurrency, acceptance
  criteria, open questions.
- `specs/003-learning-state/checklists/requirements.md` — readiness checklist.
- `.omp/decisions/2026-09-18-001-telegram-auth-account-quorum.md:149-152,241-242` — the
  User → learning `ON DELETE CASCADE` contract; `users` never imports `learning`.
- `.omp/decisions/2026-09-19-002-content-catalog-access-quorum.md:240-256` — the FK
  deletion matrix, the learning cascade carry-forward and "content never imports learning".
- `.omp/decisions/2026-09-19-004-content-api-media-review.md:185-196,255-272,319-322` —
  quiz child identity is immutable and never deleted, the answer minima that make the
  scoring denominator well defined, and the attempt-time policy carry-forward to 003.
- `PROJECT_STATE.md:85-89` — carry-forward contracts for 003.
- `../medcore-docs/content/structure.md:5-6,16-23` — `Subject → Section → Topic`; a Topic has
  any number of optional `ContentBlock` "смысловые подразделы".
- `../medcore-docs/architecture/database.md:9-20,66-73` — `Section ↓ Topic ├── ContentBlock`;
  no Topic→Section child relation.
- `../medcore-docs/decisions/0004-mvp-decision-register.md:92-103,176-178` — Topic progress
  items 66-74 (manual button, score-based auto-completion with **TBD** threshold, manual
  completion works when there are no quizzes) and item 134 (User deletion cascades
  progress/attempts).
- `../medcore-docs/decisions/0006-anonymous-demo-content.md:9-30`,
  `0007-content-access-model.md:19-64`, `0008-mvp-auth-content-and-integration-contract.md:46-65,75-77`
  — anonymous demo scope, Topic `demo/free/paid` boundary, one-or-many correct answers,
  simple card scheduling with `next_review_at`/`last_reviewed_at`/`intervals`, Topic
  deletion scope.
- `docs/architecture/target-architecture.md:67-76,96-120,145-181,198-231` — app ownership,
  allowed dependency direction (`learning → users`, `learning → content`,
  `learning.application → subscriptions.policy`), services/selectors, one atomic boundary,
  DB constraints as second line of defence, no signals, no queue.
- `docs/architecture/conventions.md:34-74,76-109,132-156` — error envelope, HTTP table,
  validation layers, transaction/constraint and physical-deletion rules.
- `docs/architecture/domain-model.md:36-41,115-127,159-190` — cardinalities, quiz semantics,
  learning lifecycle, "best score is derived", "anonymous user does not create learning
  state".
- `docs/architecture/open-questions.md:94,107-121` — flashcard/quiz/progress items; the
  nullable-Flashcard-Topic and single-correct-answer lines are stale against ADR 0008.
- Existing code: `apps/content/{models,access,selectors,services,serializers,views,urls}.py`,
  `apps/content/migrations/0003_content_api_entities.py`,
  `apps/common/{exceptions,permissions,pagination}.py`, `apps/users/{models,authentication,throttles}.py`,
  `apps/subscriptions/policy.py`, `config/settings/base.py`, `config/urls.py`,
  `apps/content/tests/*` (90 tests green at `f30b1e4`), `apps/learning/` (empty skeleton).

## Manager review findings (the gaps the spec leaves open)

1. The spec's "theory section" has no counterpart in the accepted content model: `Section`
   is the **parent** of `Topic` (`apps/content/models.py:51-73,87-89`), so "Section must
   belong to the requested Topic" is unsatisfiable and "Topic has zero sections" is
   unreachable (a Topic always has one non-null parent Section).
2. `answers_state` shape is explicitly delegated to plan/OpenAPI
   (`specs/003-learning-state/spec.md:195-196,377-379`) while the same sentence restricts it
   to "only answer IDs".
3. The attempt-time content-change policy ("blocked or a new attempt policy") and the
   aggregate-deletion policy are delegated to 003 by 004 and `PROJECT_STATE.md`.
4. Progress transitions versus the accepted register: manual completion is accepted, and
   score-based auto-completion is accepted **with a TBD threshold** (register items 67-68),
   while the spec says a pass does not complete the topic in this feature.
5. Best score is derived with no named surface in the spec's route list.
6. `TOPIC_ACCESS_DENIED` does not exist in the implementation; the real codes are
   `AUTHENTICATION_REQUIRED` and `TOPIC_ENTITLEMENT_REQUIRED` (`apps/content/access.py:25-47`).
7. The learning app has no throttle scopes, no urls include and no tests directory.

## Luna escalation

One bounded round was run (trigger 4: accepted decisions/architecture/spec disagree;
trigger 5: migration, concurrency and destructive-semantics decisions needed a second
opinion). Packet: `local://003-spec-review-packet.md` (session-local), evidence paths and
lines as listed above. Luna stayed read-only.

| Item | Verdict | Substance |
|---|---|---|
| Q1 theory unit | `RESOLVED` | Accept `UserTopicBlockProgress` and `/blocks/{block_id}/complete/`; count published blocks only; the FK/service must verify `block.topic_id == topic_id`; `Section` deletion stays `PROTECT` through the parent hierarchy. |
| Q2.1 `answers_state` | `BLOCKED` | The literal "only answer IDs" contract forbids the proposed `question_ids`/`results`/`score_percent` inside it; remedy: move the frozen question set and the graded results into separate fields, keeping `answers_state` answer-ID-only, **or** explicitly amend the spec/OpenAPI to permit question IDs and numeric scores. |
| Q2.2 grading policy | `RESOLVED` | Freeze the question set at start, grade with the current correctness flags at submit, persist the results; no snapshot of texts, no blocked content edits; "incompatible" means a change to the frozen membership/IDs. |
| Q2.3 deletion | `RESOLVED` | All learning FKs `CASCADE`; no orphan rows; no retention. |
| Q2.4 active attempt | `RESOLVED` | Partial unique constraint + locked read; a normal `POST` with an existing active attempt returns 200, creation returns 201, and `409 ACTIVE_ATTEMPT_EXISTS` is only the racing loser. |
| Q2.5 scoring | `RESOLVED` | Exact rational arithmetic, unanswered = 0, one `ROUND_HALF_UP` rounding at the boundary, `passed = score >= 80` as a display threshold only. |
| Q2.6 schedule/due | `RESOLVED` | `(1, 3, 7, 14, 30)`; `know` advances one interval, `repeat` resets; due = existing rows with `next_review_at <= now` on published, accessible topics; never-reviewed cards have no row. |
| Q2.7 progress | `BLOCKED` | Manual-only completion contradicts register item 67; the 80% display threshold contradicts spec rule 21; an accepted deferral/amendment or a separately agreed threshold is required. |
| Q2.8 best score | `RESOLVED` | Derived `Max` over the current user's submitted attempts, exposed on quiz detail and the topic quiz list; null when there is no submitted attempt. |
| Q2.9 errors | `RESOLVED` | Drop the stale `TOPIC_ACCESS_DENIED`; use `RESOURCE_NOT_FOUND` for missing/unpublished/hidden, `AUTHENTICATION_REQUIRED` for anonymous, `TOPIC_ENTITLEMENT_REQUIRED` for paid denial. |
| overall | `BLOCKED` | Q2.1 and Q2.7 unresolved at the time of the verdict. |

### Deliberation and rebuttal (how the two blockers were closed)

The manager adopted the remedies Luna named instead of re-arguing the rejected shapes.

**Q2.1 — the answer-ID-only contract is kept literally; the extra state gets its own
fields.** `QuizAttempt` stores three separate values: `answers_state` (JSON,
`{"selected_answer_ids": [int, ...]}` — answer IDs only, exactly as the spec requires),
`question_ids` (JSON list of the question IDs frozen at attempt start) and `results` (JSON,
null while active; after submit a list of `{"question_id", "selected_answer_ids",
"correct_answer_ids", "score_percent"}`). The wire contract exposes `selected_answer_ids`,
`question_ids`, `questions` (current content restricted to the frozen set, never carrying
`is_correct` while the attempt is active) and `results` (submitted only). The spec's
QuizAttempt field list and the "must contain only answer IDs" sentence are amended
explicitly in `specs/003-learning-state/spec.md`; the shape is documented in the feature's
`contracts/learning-api.md`, `data-model.md` and the OpenAPI, so nothing is closed
silently. This is Luna's option (a), not a reinterpretation of "only answer IDs".

**Q2.7 — score-based auto-completion is explicitly deferred; the threshold stays an owner
decision.** The accepted register requires auto-completion by test score *and* leaves the
threshold **TBD** (items 67-68). Implementing it would invent that TBD, which `AGENTS.md`
forbids; using the spec's 80% display threshold would contradict spec rule 21. The
manager therefore implements the accepted manual completion (register items 66 and 69) and
records the deferral explicitly in the spec (`Out of scope` and business rule 21) and in
this record, together with the open owner decision: **the score threshold and the
score-based transition for `learned` remain unaccepted product parameters and must be
resolved by the owner before that behavior can ship.** No canonical `medcore-docs` file is
rewritten; the register items stay accepted-but-unscheduled with their TBD intact. This is
Luna's "explicit deferral" remedy, recorded rather than silent.

## Final decision

### 1. Theory progress is block-based

- `UserTopicBlockProgress(user, topic, block, is_complete, completed_at, created_at,
  updated_at)`: `block → content.ContentBlock` `CASCADE`, `topic → content.Topic` `CASCADE`,
  unique `(user, block)`, index on `(user, topic)`.
- API: `GET`/`PATCH /api/v1/topics/{topic_id}/progress/` and
  `POST /api/v1/topics/{topic_id}/blocks/{block_id}/complete/`. The service resolves the
  topic from the block and rejects a mismatched pair with 404 `RESOURCE_NOT_FOUND`, so a
  moved block can never create an inconsistent `(topic, block)` pair.
- `total_units` = the Topic's published `ContentBlock` rows; `completed_units` = the user's
  completed rows whose block is published; `theory_percent` = `ROUND_HALF_UP(100 ×
  completed/total)`, `0` when `total == 0`. A deleted block removes its row through the FK
  cascade; the spec's "Section is deleted after progress exists" edge case is satisfied by
  the block cascade.
- The 002 carry-forward keeps its invariant: every learning FK is `ON DELETE CASCADE` and
  `content` never imports `learning`. No learning row references `Section`; `Section`
  deletion remains impossible while a Topic references it (`Topic.section` `PROTECT`).

### 2. Progress transitions

- The first learning action on an accessible Topic creates `UserTopicProgress` with
  `status=learning` and `started_at`; `last_opened_at` is written by the progress `PATCH`
  `{"opened": true}`.
- `learned` is reached only through the explicit `PATCH {"status": "learned"}` transition
  (register items 66 and 69: the manual button works, also when the topic has no quizzes).
  It never regresses, and it does not depend on the theory percentage, because the accepted
  register does not gate manual completion on content completeness.
- Score-based auto-completion is **not** implemented; see the Q2.7 deliberation and the
  residual risk section.

### 3. Flashcards

- `FlashcardReview(user, flashcard, interval_days, repetitions, last_reviewed_at,
  next_review_at, created_at, updated_at)`, unique `(user, flashcard)`, `flashcard CASCADE`,
  one current row per user/card, no review history.
- Intervals are the settings value `LEARNING_FLASHCARD_INTERVALS` (default
  `(1, 3, 7, 14, 30)` days). `know` advances exactly one interval and stays at the last one;
  `repeat` resets to the first interval; `repetitions` counts the consecutive advances since
  the last reset; `next_review_at = now + interval_days`; `last_reviewed_at = now`.
- `GET /api/v1/flashcards/review-due/` returns the current user's review rows with
  `next_review_at <= now` whose Topic is published and still accessible, ordered by
  `(next_review_at, id)`. A never-reviewed card has no row and is therefore not due.

### 4. Quiz attempts

- `QuizAttempt(user, quiz, status, answers_state, question_ids, results, score_percent,
  passed, started_at, submitted_at, updated_at)`, `user CASCADE`, `quiz CASCADE`, partial
  unique `(user, quiz)` where `status = active`.
- Start: `POST /api/v1/quizzes/{id}/attempts/` returns the existing active attempt with 200
  or creates one with 201; `question_ids` freezes the quiz's current question IDs;
  `answers_state` starts as `{"selected_answer_ids": []}`. The racing loser of a concurrent
  start gets 409 `ACTIVE_ATTEMPT_EXISTS`.
- Save: `PATCH /api/v1/quiz-attempts/{id}/` with `{"selected_answer_ids": [...]}` replaces
  the whole selection (idempotent retry); IDs outside the attempt's quiz or outside the
  frozen question set are 422 `INVALID_ANSWER`; a submitted attempt is 409
  `ATTEMPT_ALREADY_SUBMITTED`.
- Submit: `POST /api/v1/quiz-attempts/{id}/submit/` locks the row, requires `active`,
  grades the frozen question set against the current content, persists `results`,
  `score_percent`, `passed` and `submitted_at` in one transaction, and returns the frozen
  result. A concurrent second submit gets 409.
- Scoring: per question `max(0, (correct_selected - incorrect_selected) /
  correct_answer_count)` with exact rational arithmetic; unanswered questions score 0; the
  quiz score is the arithmetic mean over the frozen question set as a percentage with one
  `ROUND_HALF_UP` rounding; `passed = score_percent >= 80` (`LEARNING_QUIZ_PASS_PERCENT`).
- Best score is derived (`Max` over the user's submitted attempts) and exposed as
  `best_score_percent` on `GET /api/v1/quizzes/{id}/` and the topic quiz list; `null` when
  the user has no submitted attempt.

### 5. Access, ownership and errors

- Every learning endpoint requires a Bearer user JWT (`IsAuthenticated`); the integration
  principal is an `AnonymousUser` and is therefore rejected.
- Every read and write resolves the published Topic (`content.selectors.get_published_topic`)
  and re-evaluates `content.access.evaluate_topic_access`; a missing or unpublished topic and
  another user's object are 404 `RESOURCE_NOT_FOUND`, a paid topic without entitlement is
  403 `TOPIC_ENTITLEMENT_REQUIRED`. `TOPIC_ACCESS_DENIED` is removed from the spec as stale.
- Throttle scopes added to `config/settings/base.py`: `learning_read` 120/min,
  `learning_progress` 60/min, `learning_review` 60/min, `learning_attempt` 60/min.
- The learning app registers no Django Admin (inspecting other users' learning state is a
  separate admin feature).

## Rejected alternatives

- **Literal `Section` progress** (FK to the Topic's parent Section): makes "Topic has zero
  sections" unreachable, makes "Section must belong to the requested Topic" unsatisfiable and
  reduces the percentage to 0/100. Rejected with Luna's agreement.
- **A new Topic→Section content entity**: new domain model and a new content migration,
  neither authorized nor needed; a Topic's theory units already exist as ContentBlocks.
- **`answers_state` carrying the frozen question IDs and the graded results**: contradicts
  the literal "only answer IDs" sentence; rejected in favour of separate fields plus an
  explicit spec amendment.
- **Blocking content edits while an attempt is active**: not required by any accepted source
  and it would couple `content` writes to `learning` state; the frozen question set plus the
  persisted results give the same reproducibility without a cross-domain check.
- **Storing `best_score_percent`**: contradicts register/domain-model "best score is derived".
- **Inventing the auto-completion threshold or reusing 80% for it**: invents a TBD and
  contradicts spec rule 21.
- **Auto-transition to `learned` when all theory blocks are complete**: would make the spec's
  explicit manual `learned` transition unreachable and would gate manual completion on
  content completeness, which the register does not require.
- **Django Admin registration for learning models**: out of scope; separate admin feature.

## Residual risk

- **Open owner decision**: score-based automatic topic completion (register items 67-68)
  stays unimplemented because its threshold is TBD; the 80% value is a per-attempt display
  threshold only. The owner must accept a threshold before that behavior ships.
- A content edit to `is_correct` while an attempt is active changes that attempt's grading;
  after submit the persisted results make the score reproducible. This is the policy Luna
  accepted as an MVP risk.
- An author adding a question to a quiz does not affect an in-flight attempt (the frozen
  question set), so the quiz detail and an active attempt can briefly show different question
  sets; the client resumes from the attempt payload.
- `paid` topics remain unreachable until the subscriptions feature supplies the entitlement
  source; the deny path is real and the allow path is exercised through the policy seam.
- The spec amendment (block-based progress, the `QuizAttempt` field list, the error-code
  reconciliation, the auto-completion deferral) is recorded here; no canonical
  `medcore-docs` file is modified.
- Physical deletion of content or a User removes learning rows by cascade; no retention,
  tombstone or export is added.

## State transition and validation/rollback consequence

With this record and the focused spec amendment written, the workflow advances
`SPEC_REVIEW` → `READY_FOR_PLAN`; the manager may produce plan/tasks and then implement on
`feature/003-learning-state`. Implementation must prove: model constraints and the partial
unique active attempt, the cascade matrix for User/Topic/Block/Flashcard/Quiz deletion, the
progress percentage boundary and idempotent block completion, the manual `learned`
transition and its non-regression, the flashcard schedule matrix and the due selector, quiz
start/resume/validation/submit/retake with no correctness leak before submit, partial-score
boundaries and `ROUND_HALF_UP`, derived best score, ownership/access/anonymous denial,
concurrent start/submit/review conflicts, throttling, secret-safe logs and OpenAPI; then run
the full `AGENTS.md` validation suite. A source conflict, security invariant or
migration-compatibility issue stops the affected change and is recorded as `BLOCKED`.
Migrations are forward-only; a failed implementation is reverted on the unpushed feature
branch, never by rewriting applied migration history.

## Final review verdicts

- DeepSeek manager review: `READY_FOR_PLAN` after this record and the spec amendment; every
  gap resolved from a higher-priority source or explicitly deferred.
- Luna watchdog round 1: `BLOCKED` on Q2.1 and Q2.7, `RESOLVED` on Q1 and Q2.2-Q2.6, Q2.8,
  Q2.9. Both blockers are closed by the remedies Luna named (separate persisted fields plus
  an explicit spec amendment; explicit recorded deferral of the TBD-threshold behavior), so
  no second round was run within the two-round budget.

## Post-analysis corrections (`ANALYZED`, 2026-09-19)

A read-only `spec-reviewer` consistency analysis ran on the spec, plan, tasks, research,
data model and contract before implementation. It returned `NOT_READY` with one `BLOCKER`,
eight `HIGH` and eleven lower findings. Every finding is closed in the artifacts; the four
material corrections are recorded here.

1. **`BLOCKER` — the 80% pass threshold is dropped from the feature.** The draft spec's rule
   21 and the first revision of this record carried `passed = score >= 80`. That value comes
   from the frontend prototype, and the accepted sources say the opposite: the register
   states "Проходной процент глобально пока не вводить"
   (`../medcore-docs/decisions/0004-mvp-decision-register.md:90`, item 65),
   `../medcore-docs/architecture/database.md:125` and `../medcore-docs/ai/context.md:132`
   state that no global pass threshold exists, and `docs/architecture/open-questions.md:116-118`
   records that the backend source of truth for the threshold is not chosen while the
   prototype's 80% is not a contract (`specs/003-learning-state/spec.md:367`). Q2.5 of this
   record accepted the value without reconciling item 65; that is corrected now.
   **Decision**: `QuizAttempt` has no `passed` column, `LEARNING_QUIZ_PASS_PERCENT` is not
   introduced, and `submit` returns `score_percent` plus the per-question `results` only.
   The pass threshold is an **open owner decision** that gates both a pass/fail display and
   the score-based automatic completion deferred in Q2.7. This removes an invented product
   parameter; it does not remove any spec scope (the spec's `Scope` list never contained a
   pass flag).
2. **`HIGH` — the flashcard review action must move the Topic to `learning`.** Spec business
   rule 5 ("First theory-block/card/quiz action transitions topic progress to learning") was
   implemented for blocks and attempts but not for reviews; the contract, T008 and T009 now
   require the `touch_topic_learning` transition and assert it.
3. **`HIGH` — anonymous quiz reads are denied, and the narrowing is recorded.** The spec's
   permission table gave anonymous "access policy" for `read quiz` while the same spec's API
   header says every route requires a Bearer token, and this record's §5 requires
   authentication on every learning route. Anonymous demo content is served by the 002
   surface (`/api/v1/topics/{id}/content/`); the learning quiz/flashcard reads expose the
   learning surface and stay authenticated. The spec table is amended to `deny` for anonymous.
4. **`HIGH` — `UserTopicBlockProgress` keeps no redundant `topic` column.** The content API
   can re-parent a block to another Topic
   (`apps/content/services.py:495-496`), so a stored `(topic, block)` pair could go stale.
   The row now references only the block, and every topic-scoped read derives the topic from
   `block__topic` with `block__status=published`; the route still validates that the URL
   topic matches `block.topic_id` (404 otherwise). The spec's data model is amended
   accordingly, and the derived counts are computed from the block side.

Also closed: the zone tables in `plan.md` and `tasks.md` are unified on the
`Z1-foundation` / `Z2-progress` / `Z3-flashcards` / `Z4-quizzes` mapping; the URL assembly
moved to a foundation step that creates empty sub-package URL modules which the feature
zones then fill, so the foundation checkpoint is reachable; the per-question
`score_percent` is declared display-rounded with the stored total authoritative; the
inactive-user error row uses `AUTH_USER_INACTIVE`; the submit-validation wording, the
"learning row never references a deleted object" invariant and the contract's 404/403
wording are corrected; the Q2.2 policy gains an explicit `is_correct`-flip test; the
quickstart notes the `OPENAPI_PUBLIC` prerequisite.

## Residual risk after the corrections

- The pass threshold, the pass/fail display and the score-based automatic completion all
  depend on one owner decision; none of them ships in this feature.

## Post-implementation review and fixes (`REVIEWING`, 2026-09-19)

Two independent read-only review passes ran on the finished diff before delivery.

- DeepSeek `senior-reviewer`: `BLOCKED` on one defect — `review_flashcard` read the current
  `FlashcardReview` row without a row lock and then saved unconditionally, so two concurrent
  `know` actions lost a schedule step (spec Transactions/Concurrency rules and the
  "serialized against the latest current row" edge case). The existing concurrency test only
  asserted "one row", so it passed with the defect present. Non-blocking findings: the
  contract artifacts still mentioned a persisted `passed`, no OpenAPI schema assertion
  existed, `QuizAttemptDetailView.get_throttles` indexed a dict by method (HEAD/OPTIONS →
  `KeyError` → 500 outside the error envelope), the three empty-body POST routes ignored
  unknown fields, and cross-user isolation/throttle coverage was missing for flashcards and
  progress.
- DeepSeek `security-reviewer`: `READY`, no exploitable defect. It independently reported the
  same lost-update finding plus a second contract-critical race — the `UserTopicProgress`
  read-modify-write could roll a `learned` topic back to `learning` (contract: "`learned`
  never regresses") — and one bounded-input finding (an unbounded `selected_answer_ids` list
  could reach the PostgreSQL bind-parameter limit and return 500 instead of 422). It recorded
  as informational (accepted by the contract) that a submit reveals the correct answer IDs
  and that retakes are unlimited, so the control only protects correctness *before* the first
  submit.

One fixes worker closed every actionable finding: `select_for_update()` in
`_find_review`; conditional `UPDATE` transitions for the progress row (and removing the
`mark_topic_learned` window where the row was first committed as `not_started`);
a safe throttle-scope default; a `max_length` on the selection list; a strict
`EmptyBodySerializer` on the three empty-body routes; an OpenAPI assertion test; and the
missing isolation/throttle tests. Both race fixes carry a test that fails when the fix is
reverted (the reviewer-visible `AssertionError: 3 != 7` and
`AssertionError: 'learning' != LEARNED` respectively). The two doc mentions of a persisted
`passed` were corrected by the manager.

Accepted residual risk (owner decision, not a defect): after the first submit the attempt
payload exposes the correct answer IDs while retakes stay unlimited; if that is unwanted,
either stop returning `correct_answer_ids` or bound the retakes — both change the product
contract.
