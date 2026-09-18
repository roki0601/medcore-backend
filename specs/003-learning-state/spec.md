# Spec: Learning state, flashcard review and quizzes

Status: Draft

Owning app: learning

Risk: High

Related architecture: docs/architecture/domain-model.md,
docs/architecture/auth-and-access.md

Related decisions: medcore-docs/decisions/0008-mvp-auth-content-and-integration-contract.md

## Goal

Сохранить персональный прогресс пользователя по темам, дать ручное завершение
теоретических секций, простое планирование повторения карточек и полноценные
повторяемые quiz attempts с несколькими правильными ответами.

## Scope

- Authenticated Topic progress.
- Explicit section completion.
- Topic progress status and theory percentage.
- FlashcardReview current state per user/card.
- Actions «Знаю» and «Повторить» with simple schedule.
- Multiple Quiz per Topic.
- Questions with one or several correct answers.
- Shuffled question/answer presentation.
- Resumable active attempt and unlimited completed retakes.
- Partial score with no negative result.
- Best score derived from attempts.

## Out of scope

- Anonymous progress or guest attempts.
- FSRS or adaptive spaced repetition.
- Review event history.
- Timeout.
- Subscription/payment logic.
- Global aggregate score combining theory, cards and quizzes.
- AI generation of questions.
- Frontend state implementation.

## Actors

| Actor | Разрешённые действия |
|---|---|
| anonymous | читать разрешённый demo content, не создавая learning state |
| user | создавать и изменять собственный progress, reviews and attempts |
| editor | редактировать content, но не learning state других пользователей |
| admin | системный доступ, но user-facing learning state остаётся user-owned |

## User scenarios

### User Story 1 — theory progress (P1)

Авторизованный пользователь отмечает секции темы изученными и видит прогресс.

Acceptance scenarios:

1. Given authenticated user and accessible Topic, when user marks a section
   complete, then one user-owned section state is persisted.
2. Given completed sections and total sections, when progress is requested, then
   theory percentage equals completed sections divided by total sections.
3. Given anonymous demo reading, when no access token exists, then no progress row
   is created.

### User Story 2 — flashcard review (P1)

Пользователь отвечает на карточку действиями «Знаю» или «Повторить».

Acceptance scenarios:

1. Given a Topic-owned Flashcard and no review state, when user chooses Repeat,
   then a current review row is created with next_review_at.
2. Given a review state, when user chooses Know, then interval and next_review_at
   advance according to the simple schedule.
3. Given an existing review state, when user chooses Repeat, then the schedule is
   reset/decreased and the same current row is updated.

### User Story 3 — quiz attempt (P1)

Пользователь проходит один из нескольких quiz темы, может продолжить и повторить
попытку.

Acceptance scenarios:

1. Given accessible Quiz, when user starts it, then one active attempt is created.
2. Given active attempt, when user saves selected answers, then progress can be
   resumed later.
3. Given submitted attempt with multiple correct answers, when score is computed,
   then correct selections earn partial credit, wrong selections reduce credit,
   and question score never becomes negative.
4. Given completed attempt, when user starts again, then a separate attempt is
   retained.
5. Given anonymous user, when user tries to create attempt, then request fails
   and no attempt is created.

## Entities

- UserTopicProgress: current progress for User and Topic.
- UserTopicSectionProgress: explicit completion state for one User, Topic and
  Section.
- FlashcardReview: current scheduler state for one User and Flashcard.
- QuizAttempt: one started/submitted attempt for User and Quiz.
- Content entities Topic, Section, Flashcard, Quiz, Question and Answer are
  owned by content; learning references them and does not author them.

## Business rules

1. All learning state requires authenticated User.
2. User can access learning state only for own User.
3. Learning endpoints re-check Topic access before exposing or mutating state.
4. Topic progress statuses are not_started, learning and learned.
5. First section/card/quiz action transitions topic progress to learning.
6. Explicit completion of all available theory sections makes theory percentage
   100 percent; no cross-mode aggregate is exposed by this feature.
7. A Topic can be empty; percentage for zero sections is 0 and cannot be marked
   complete through a nonexistent section.
8. Flashcard belongs to exactly one Topic.
9. One current FlashcardReview exists per User and Flashcard.
10. Repeat and Know update the current review row rather than append history.
11. Initial scheduler uses configurable simple intervals [1, 3, 7, 14, 30] days.
12. Repeat sets the schedule to the first interval; Know advances one interval,
    staying at the last interval after reaching it.
13. Topic can contain multiple Quiz.
14. Each QuizQuestion has at least two answers and at least one correct answer.
15. A question can have one or several correct answers.
16. Quiz and answer order can be shuffled for presentation; persisted IDs remain
    stable.
17. One active unfinished attempt is allowed per User and Quiz.
18. Completed attempts are immutable and retakes are unlimited.
19. No quiz timeout is applied.
20. Per-question partial score is:
    max(0, (correct_selected - incorrect_selected) / correct_answer_count).
    Quiz score is the arithmetic average of question scores, represented as a
    percentage rounded to the nearest whole number.
21. Pass threshold is 80 percent for attempt result display; pass status does
    not by itself complete Topic progress in this feature.
22. Best score is derived from completed attempts and is not stored separately.

## Invariants

- Unique UserTopicProgress per User and Topic.
- Unique UserTopicSectionProgress per User and Section within a Topic.
- Unique current FlashcardReview per User and Flashcard.
- At most one active QuizAttempt per User and Quiz.
- Completed QuizAttempt cannot be mutated.
- Anonymous requests never create or update learning state.
- A learning row cannot reference an inaccessible or deleted content object.

## Data model

### UserTopicProgress

- user: required User foreign key.
- topic: required Topic foreign key.
- status: not_started, learning, learned.
- last_opened_at: nullable UTC timestamp.
- started_at: nullable UTC timestamp.
- completed_at: nullable UTC timestamp.
- created_at, updated_at: UTC timestamps.

### UserTopicSectionProgress

- user: required User foreign key.
- topic: required Topic foreign key.
- section: required Section foreign key.
- is_complete: boolean.
- completed_at: nullable UTC timestamp.
- unique user/topic/section.

### FlashcardReview

- user: required User foreign key.
- flashcard: required Flashcard foreign key.
- interval_days: non-negative integer.
- repetitions: non-negative integer.
- last_reviewed_at: nullable UTC timestamp.
- next_review_at: nullable UTC timestamp.
- created_at, updated_at: UTC timestamps.

### QuizAttempt

- user: required User foreign key.
- quiz: required Quiz foreign key.
- status: active or submitted.
- answers_state: compact current selected-answer state for resumable active
  attempts and final submitted result.
- score_percent: nullable until submitted.
- passed: nullable until submitted.
- started_at, submitted_at, updated_at: UTC timestamps.

The exact serialized answers_state shape must be documented in the API schema
and must contain only answer IDs, not copied question text or sensitive data.

## API

All URLs use /api/v1/ and require Bearer access token unless noted.

### Topic progress

- GET /api/v1/topics/{topic_id}/progress/
- PATCH /api/v1/topics/{topic_id}/progress/
- POST /api/v1/topics/{topic_id}/sections/{section_id}/complete/

Progress response includes topic status, theory percentage, completed section
count and total section count. PATCH supports opening/starting state and explicit
manual learned transition only where allowed by the service.

### Flashcards

- GET /api/v1/topics/{topic_id}/flashcards/
- GET /api/v1/flashcards/{id}/
- GET /api/v1/flashcards/review-due/
- POST /api/v1/flashcards/{id}/review/

Review request:

    {
      "action": "know"
    }

Allowed actions are know and repeat. Response returns current review state and
next_review_at.

### Quizzes

- GET /api/v1/topics/{topic_id}/quizzes/
- GET /api/v1/quizzes/{id}/
- POST /api/v1/quizzes/{id}/attempts/
- GET /api/v1/quiz-attempts/{id}/
- PATCH /api/v1/quiz-attempts/{id}/
- POST /api/v1/quiz-attempts/{id}/submit/

Start returns the existing active attempt with 200, or creates one with 201 when
no active attempt exists. PATCH saves selected answer IDs. Submit freezes the
attempt and returns score, passed, per-question result visibility and timestamps.

User API returns only questions/answers allowed by Topic access and only
published content. It does not expose answer correctness before submit.

## Permissions

| Operation | anonymous | user | editor | admin |
|---|---:|---:|---:|---:|
| read own progress | deny | own only | own only | own only by default |
| mutate own progress | deny | own only | own only | own only by default |
| read flashcard review | deny | own only | own only | own only by default |
| review flashcard | deny | own only | own only | own only by default |
| read quiz | access policy | access policy | access policy | access policy |
| start/save/submit attempt | deny | own only | own only | own only by default |
| inspect other users' learning state | deny | deny | deny | separate admin feature |

Role does not bypass Topic access policy for user-facing endpoints.

## Validation

- Topic, Section, Flashcard and Quiz must exist and be accessible.
- Section must belong to the requested Topic.
- Review action must be know or repeat.
- Attempt PATCH accepts only answer IDs belonging to the attempt's Quiz.
- Attempt cannot save after submission.
- Submit requires all required question decisions according to Quiz contract;
  unanswered questions receive zero.
- At least two answers and one correct answer are required for each question.
- Score is bounded to 0–100 and rounded only at final response/storage boundary.

## Errors

| Condition | HTTP | Code |
|---|---:|---|
| missing/expired auth | 401 | AUTHENTICATION_REQUIRED |
| inaccessible Topic | 403 or 404 | TOPIC_ACCESS_DENIED or RESOURCE_NOT_FOUND |
| duplicate active attempt | 409 | ACTIVE_ATTEMPT_EXISTS |
| submitted attempt mutation | 409 | ATTEMPT_ALREADY_SUBMITTED |
| answer belongs to another Quiz | 422 | INVALID_ANSWER |
| invalid review action | 422 | VALIDATION_ERROR |
| missing learning object | 404 | RESOURCE_NOT_FOUND |
| throttled learning action | 429 | THROTTLED |

All errors use code, detail and optional fields. No answer correctness is leaked
before quiz submit.

## Edge cases

- Topic has zero sections: theory percentage is 0.
- Section is deleted after progress exists: progress cleanup follows Topic
  deletion and does not leave an orphan row.
- User clicks review action twice: the second request is serialized against the
  latest current row and does not create duplicate state.
- User opens the same Quiz twice concurrently: one active attempt wins and the
  other receives ACTIVE_ATTEMPT_EXISTS.
- User submits no answers: score is 0 and attempt is submitted.
- User selects all answers including wrong ones: partial formula applies and
  score cannot be negative.
- Quiz content changes after attempt start: attempt keeps stable question/answer
  IDs; incompatible content changes are blocked or require a new attempt policy.
- User loses network while saving: retrying the same PATCH is safe because it
  replaces current answer state.

## Transactions

- Section completion and Topic progress transition are one transaction.
- Flashcard review action locks or safely updates the current review row in one
  transaction.
- Starting an attempt and enforcing one-active-attempt invariant are atomic.
- Saving active attempt state is atomic.
- Submit computes and freezes score in one transaction.
- Content deletion cascades learning data only as explicitly approved by the
  content deletion contract.

## Concurrency

- Unique constraints protect progress/review/active-attempt invariants.
- Use row locking or equivalent atomic conditional update for review and submit.
- A second concurrent submit receives a stable conflict and cannot rewrite score.

## Background jobs/events

None. Review scheduling and quiz scoring are synchronous.

## Security

- Learning endpoints require authentication and object ownership.
- Backend checks Topic access on every read and write.
- Do not expose answer correctness before submit.
- Validate all submitted IDs against the current Quiz.
- Do not log selected answers if payloads may contain sensitive study data;
  log safe attempt/user IDs and failure codes.
- Apply throttling to review, attempt save and submit endpoints.

## Risks, compatibility and rollout

- The frontend prototype's formula and guest limits are not used as contract.
- Existing learning app is a skeleton; new migrations and service boundaries are
  required.
- Quiz content mutation during active attempts needs a plan-time migration/
  locking decision if editors can modify published questions.
- Subscription entitlement remains an external policy dependency.

## Acceptance criteria

1. Anonymous usage never creates learning state.
2. Authenticated users can complete sections and see deterministic theory
   percentage.
3. One current review row exists per user/card and actions update its schedule.
4. Multiple quizzes and multiple correct answers are supported.
5. Attempts can be resumed, submitted once and repeated without overwriting
   previous completed attempts.
6. Partial scores are bounded and reproducible.
7. Backend enforces ownership, Topic access and answer validity.
8. Concurrency tests prove the active-attempt and review invariants.

## Test scenarios

- Progress model uniqueness and status transitions.
- Section completion and zero-section boundary.
- Anonymous denial and user ownership.
- Flashcard first review, know/repeat schedule and concurrent clicks.
- Quiz start, resume, invalid answer IDs and active duplicate.
- Single/multiple correct answer scoring and negative-score boundary.
- Submit idempotency/conflict and retake.
- Content access and unpublished question filtering.
- Throttling and safe error/log behavior.

## Dependencies

- Auth/session contract from spec 001.
- Content entities and access policy from spec 002.
- Subscription policy interface for paid Topic checks.
- PostgreSQL transaction and migration support.

## Open questions

None for the agreed MVP behavior. Exact serializer field naming for
answers_state is an API design detail that must be fixed in the plan/OpenAPI
before implementation.
