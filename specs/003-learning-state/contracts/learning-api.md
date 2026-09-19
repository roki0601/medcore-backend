# Contract: Learning API

Feature: `003-learning-state`. Prefix `/api/v1/`, REST/JSON, Bearer access token
on every route, DRF page-number pagination (`page`, `page_size`, default 20,
maximum 100) on list routes, the shared error envelope
`{"code", "detail", "fields"}`.

Decision record: [delegated review](../../.omp/decisions/2026-09-19-003-learning-state-review.md).

## Routes, names and view classes

| Route | URL name | View class (module) | Throttle scope |
|---|---|---|---|
| `GET/PATCH /api/v1/topics/<int:topic_id>/progress/` | `learning-topic-progress` | `TopicProgressView` (`apps.learning.progress.views`) | `learning_read` / `learning_progress` |
| `POST /api/v1/topics/<int:topic_id>/blocks/<int:block_id>/complete/` | `learning-topic-block-complete` | `TopicBlockCompleteView` (`apps.learning.progress.views`) | `learning_progress` |
| `GET /api/v1/topics/<int:topic_id>/flashcards/` | `learning-topic-flashcards` | `TopicFlashcardListView` (`apps.learning.flashcards.views`) | `learning_read` |
| `GET /api/v1/flashcards/review-due/` | `learning-flashcard-review-due` | `FlashcardReviewDueView` (`apps.learning.flashcards.views`) | `learning_read` |
| `GET /api/v1/flashcards/<int:pk>/` | `learning-flashcard-detail` | `FlashcardDetailView` (`apps.learning.flashcards.views`) | `learning_read` |
| `POST /api/v1/flashcards/<int:pk>/review/` | `learning-flashcard-review` | `FlashcardReviewView` (`apps.learning.flashcards.views`) | `learning_review` |
| `GET /api/v1/topics/<int:topic_id>/quizzes/` | `learning-topic-quizzes` | `TopicQuizListView` (`apps.learning.quizzes.views`) | `learning_read` |
| `GET /api/v1/quizzes/<int:pk>/` | `learning-quiz-detail` | `QuizDetailView` (`apps.learning.quizzes.views`) | `learning_read` |
| `POST /api/v1/quizzes/<int:pk>/attempts/` | `learning-quiz-attempt-start` | `QuizAttemptStartView` (`apps.learning.quizzes.views`) | `learning_attempt` |
| `GET/PATCH /api/v1/quiz-attempts/<int:pk>/` | `learning-quiz-attempt-detail` | `QuizAttemptDetailView` (`apps.learning.quizzes.views`) | `learning_read` / `learning_attempt` |
| `POST /api/v1/quiz-attempts/<int:pk>/submit/` | `learning-quiz-attempt-submit` | `QuizAttemptSubmitView` (`apps.learning.quizzes.views`) | `learning_attempt` |

Each sub-package owns its `urls.py`; `apps/learning/urls.py` includes the three
sub-modules and `config/urls.py` includes the app under `/api/v1/`. A view that
serves two methods with different scopes implements `get_throttles()` explicitly
and documents both in `extend_schema`.

## Common rules

- Authentication: `IsAuthenticated`; the integration principal is an
  `AnonymousUser`, so presenting the integration key yields 401
  `AUTHENTICATION_REQUIRED`.
- Ownership: a user can read and mutate only their own learning state. Another
  user's attempt is 404 `RESOURCE_NOT_FOUND`, never 403, so existence is not
  leaked.
- Access: every route resolves the published Topic
  (`content.selectors.get_published_topic`) and re-evaluates
  `content.access.evaluate_topic_access`. Missing or unpublished topic → 404
  `RESOURCE_NOT_FOUND`; authenticated user without paid entitlement → 403
  `TOPIC_ENTITLEMENT_REQUIRED`.
- Unknown JSON fields in any write body → 422 `VALIDATION_ERROR` with
  `fields = {"<name>": ["Unknown field."]}`.
- Throttle scopes: `learning_read` (120/min) on reads, `learning_progress`
  (60/min), `learning_review` (60/min), `learning_attempt` (60/min).
- Logging: learning adds no payload logging of its own — no selected answers, no
  question/answer text, no tokens. Failures use the shared error envelope; if a
  future change logs, it logs attempt/user/topic/quiz IDs and failure codes only.

## Topic progress

### `GET /api/v1/topics/{topic_id}/progress/` — `learning-topic-progress`

Scope `learning_read`. Returns the derived snapshot and **creates nothing** (a
never-touched topic reports `not_started` with `null` timestamps).

```json
{
  "topic": 7,
  "status": "learning",
  "theory_percent": 50,
  "completed_blocks": 1,
  "total_blocks": 2,
  "last_opened_at": "2026-09-19T10:00:00Z",
  "started_at": "2026-09-19T09:00:00Z",
  "completed_at": null
}
```

### `PATCH /api/v1/topics/{topic_id}/progress/` — same name

Scope `learning_progress`. Body (at least one field required):

```json
{"opened": true}
{"status": "learned"}
{"opened": true, "status": "learned"}
```

- `opened: true` → `last_opened_at = now`; a missing row is created with
  `status=learning`, `started_at=now`; `not_started` becomes `learning`;
  `learned` never regresses.
- `status: "learned"` → the explicit manual transition; `completed_at = now`
  when the row was not already `learned`. Allowed for any accessible topic,
  including a topic without theory blocks or quizzes (register items 66 and 69).
- Response 200: the same payload as `GET`.
- Errors: 401 `AUTHENTICATION_REQUIRED`, 404 `RESOURCE_NOT_FOUND`, 403
  `TOPIC_ENTITLEMENT_REQUIRED`, 422 `VALIDATION_ERROR`, 429 `THROTTLED`.

### `POST /api/v1/topics/{topic_id}/blocks/{block_id}/complete/` — `learning-topic-block-complete`

Scope `learning_progress`. Empty body. Resolves the Topic from the block; a
`block.topic_id != topic_id` pair is 404 `RESOURCE_NOT_FOUND`, and the block must
be a published block of the Topic.

- 201 on the first completion of that block, 200 on a repeat (idempotent, the row
  is updated, never duplicated).
- Creates the `UserTopicProgress` row with `status=learning` when missing;
  `learned` never regresses.
- Response: the `GET` progress payload.
- Errors as above.

## Flashcards

### `GET /api/v1/topics/{topic_id}/flashcards/` — `learning-topic-flashcards`

Scope `learning_read`. Paginated list of the Topic's flashcards in
`(position, id)` order, each with the current user's review row:

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 11,
      "topic": 7,
      "question": "Which beta-lactam ...?",
      "answer": "Ampicillin ...",
      "position": 1,
      "review": {
        "interval_days": 3,
        "repetitions": 2,
        "last_reviewed_at": "2026-09-19T09:00:00Z",
        "next_review_at": "2026-09-22T09:00:00Z"
      }
    }
  ]
}
```

`review` is `null` when the user has never reviewed the card.

### `GET /api/v1/flashcards/{id}/` — `learning-flashcard-detail`

Scope `learning_read`. Same item shape as above. 404 for a missing flashcard or a
flashcard whose Topic is missing/unpublished; a `paid` Topic without entitlement
is 403 `TOPIC_ENTITLEMENT_REQUIRED`, not 404.

### `GET /api/v1/flashcards/review-due/` — `learning-flashcard-review-due`

Scope `learning_read`. Paginated list of the current user's review rows with
`next_review_at <= now` whose Topic is published and still accessible, ordered by
`(next_review_at, id)`. Same item shape. A never-reviewed card has no row and is
therefore not due.

### `POST /api/v1/flashcards/{id}/review/` — `learning-flashcard-review`

Scope `learning_review`. Body:

```json
{"action": "know"}
```

Allowed actions: `know`, `repeat`. Any other value → 422 `VALIDATION_ERROR`.

- `know`: `index = min(index_of(interval_days) + 1, len(intervals) - 1)`;
  `repetitions += 1` (a first `know` lands on the first interval; the last
  interval is sticky).
- `repeat`: `index = 0`; `repetitions = 0`.
- `interval_days = intervals[index]`; `last_reviewed_at = now`;
  `next_review_at = now + interval_days`.
- One current row per user/card: 201 when created, 200 when updated.
- The Topic progress row moves to `learning` in the same transaction (spec
  business rule 5); `learned` never regresses.
- Response: the flashcard item shape with the updated `review`.
- Concurrency: a second concurrent action serializes on the same row and never
  creates duplicate state; the unique constraint is the backstop.

## Quizzes

### `GET /api/v1/topics/{topic_id}/quizzes/` — `learning-topic-quizzes`

Scope `learning_read`. Paginated list in `(position, id)` order:

```json
{
  "id": 5,
  "topic": 7,
  "title": "Beta-lactams",
  "description": "",
  "position": 1,
  "question_count": 3,
  "best_score_percent": 83
}
```

`best_score_percent` is the derived maximum over the current user's submitted
attempts (`null` when there is none).

### `GET /api/v1/quizzes/{id}/` — `learning-quiz-detail`

Scope `learning_read`. Adds the questions and answers, in `(position, id)` order,
**without** `is_correct` or any other correctness signal:

```json
{
  "id": 5,
  "topic": 7,
  "title": "Beta-lactams",
  "description": "",
  "position": 1,
  "question_count": 3,
  "best_score_percent": 83,
  "questions": [
    {
      "id": 21,
      "text": "...",
      "position": 1,
      "answers": [{"id": 41, "text": "...", "position": 1}]
    }
  ]
}
```

Presentation order is deterministic; shuffling is a client concern (004 decided
no persisted shuffle and stable IDs).

### `POST /api/v1/quizzes/{id}/attempts/` — `learning-quiz-attempt-start`

Scope `learning_attempt`. Empty body.

- Existing active attempt → 200 with that attempt.
- Otherwise create → 201. `question_ids` freezes the quiz's current question IDs
  in `(position, id)` order; `answers_state` starts empty; the Topic progress row
  moves to `learning` in the same transaction.
- Racing concurrent start: exactly one attempt wins; the loser gets 409
  `ACTIVE_ATTEMPT_EXISTS` (the partial unique constraint is the backstop).

### `GET /api/v1/quiz-attempts/{id}/` — `learning-quiz-attempt-detail`

Scope `learning_read`. Own attempt only (another user's → 404).

```json
{
  "id": 31,
  "quiz": 5,
  "topic": 7,
  "status": "active",
  "question_ids": [21, 22],
  "selected_answer_ids": [41],
  "questions": [
    {"id": 21, "text": "...", "position": 1, "answers": [{"id": 41, "text": "...", "position": 1}]}
  ],
  "results": null,
  "score_percent": null,
  "started_at": "2026-09-19T10:00:00Z",
  "submitted_at": null,
  "updated_at": "2026-09-19T10:05:00Z"
}
```

`questions` is the current content restricted to the frozen `question_ids` and
never carries `is_correct` while the attempt is active. After submit `results`
carries the frozen breakdown:

```json
{"results": [{"question_id": 21, "selected_answer_ids": [41], "correct_answer_ids": [41, 42], "score_percent": 50}],
 "score_percent": 83, "submitted_at": "2026-09-19T10:10:00Z"}
```

No `passed` field exists: register item 65 forbids introducing a global pass
percentage, so the threshold is an open owner decision (post-analysis
correction 1).

### `PATCH /api/v1/quiz-attempts/{id}/` — same name

Scope `learning_attempt`. Body:

```json
{"selected_answer_ids": [41, 42]}
```

- Replaces the whole selection (retrying the same body is safe and idempotent);
  duplicates are collapsed.
- Every ID must be an answer of the attempt's Quiz **and** belong to a question
  in the frozen `question_ids`; otherwise 422 `INVALID_ANSWER`.
- A submitted attempt → 409 `ATTEMPT_ALREADY_SUBMITTED`.
- Response 200: the attempt payload.

### `POST /api/v1/quiz-attempts/{id}/submit/` — `learning-quiz-attempt-submit`

Scope `learning_attempt`. Empty body. One transaction: lock the attempt, require
`active` (otherwise 409 `ATTEMPT_ALREADY_SUBMITTED`), grade the frozen question
set against the current content, persist `results`, `score_percent` and
`submitted_at`, return 200 with the attempt payload. A concurrent second submit
loses the lock and gets 409; the frozen score can never be rewritten.

Scoring: per question `max(0, (correct_selected - incorrect_selected) /
correct_answer_count)`, unanswered = 0; the quiz score is the arithmetic mean over
the frozen question set as a percentage rounded once with `ROUND_HALF_UP` and is
authoritative (per-question `results[].score_percent` is display-rounded). A
completed attempt is immutable; retakes are unlimited and each attempt is
retained. No pass/fail flag is computed.

## Error codes

| HTTP | Code | Trigger |
|---:|---|---|
| 401 | `AUTHENTICATION_REQUIRED` | missing/invalid/expired token, integration principal |
| 401 | `AUTH_USER_INACTIVE` | inactive user (emitted by `VersionedJWTAuthentication`) |
| 403 | `TOPIC_ENTITLEMENT_REQUIRED` | authenticated user without entitlement on a `paid` Topic |
| 404 | `RESOURCE_NOT_FOUND` | missing/unpublished Topic, block outside the Topic, missing object, another user's attempt |
| 409 | `ACTIVE_ATTEMPT_EXISTS` | concurrent start race loser |
| 409 | `ATTEMPT_ALREADY_SUBMITTED` | PATCH or submit on a submitted attempt |
| 422 | `INVALID_ANSWER` | answer ID outside the attempt's quiz or frozen question set |
| 422 | `VALIDATION_ERROR` | unknown field, invalid review action, missing PATCH field |
| 429 | `THROTTLED` | scope rate exceeded |

## OpenAPI

`drf-spectacular` must expose all eleven paths with their methods, permission
(authenticated), request/response schemas and the documented error responses. The
schema is asserted by tests, including that no active attempt payload and no quiz
detail payload contains `is_correct`.
