# Data model: Learning state

Feature: `003-learning-state`. Owning app: `learning`.
Decision record: [delegated review](../../.omp/decisions/2026-09-19-003-learning-state-review.md).

All IDs are `BigAutoField`; all timestamps are timezone-aware and stored in UTC.
Migrations are forward-only: `apps/learning/migrations/0001_initial.py` is the
first migration of the app.

## Dependency direction

```text
learning ──► users      (AUTH_USER_MODEL, FK cascade contract from 001)
learning ──► content    (Topic, ContentBlock, Flashcard, Quiz, QuizQuestion,
                         QuizAnswer, access policy, published-only selectors)
learning.application ──► content.access ──► subscriptions.policy
```

`learning` never imports `subscriptions` models or policy directly; it consumes
the access decision composed by `apps.content.access`. `content` and `users`
never import `learning`.

## UserTopicProgress

Current progress of one User in one Topic. Derived values (`theory_percent`,
completed/total block counts) are never stored.

| Field | Type | Rules |
|---|---|---|
| `user` | `FK(settings.AUTH_USER_MODEL)` | required, `on_delete=CASCADE`, `related_name="topic_progress"` |
| `topic` | `FK(content.Topic)` | required, `on_delete=CASCADE`, `related_name="user_progress"` |
| `status` | `CharField(16, choices)` | `not_started` (default) \| `learning` \| `learned` |
| `last_opened_at` | `DateTimeField` | nullable |
| `started_at` | `DateTimeField` | nullable |
| `completed_at` | `DateTimeField` | nullable |
| `created_at` / `updated_at` | `DateTimeField` | `auto_now_add` / `auto_now` |

Constraints:

- `UniqueConstraint(fields=["user", "topic"], name="learning_usertopicprogress_unique_user_topic")`
- `CheckConstraint(status in ("not_started", "learning", "learned"), name="learning_usertopicprogress_status_valid")`
- `Meta.ordering = ("id",)`

## UserTopicBlockProgress

Explicit completion of one theory unit. The theory unit is the Topic's
`ContentBlock` (the accepted content model has no Section inside a Topic; see the
decision record §1).

| Field | Type | Rules |
|---|---|---|
| `user` | `FK(settings.AUTH_USER_MODEL)` | required, `CASCADE`, `related_name="topic_block_progress"` |
| `block` | `FK(content.ContentBlock)` | required, `CASCADE`, `related_name="user_progress"` |
| `is_complete` | `BooleanField` | default `False` |
| `completed_at` | `DateTimeField` | nullable |
| `created_at` / `updated_at` | `DateTimeField` | `auto_now_add` / `auto_now` |

Constraints:

- `UniqueConstraint(fields=["user", "block"], name="learning_usertopicblockprogress_unique_user_block")`
- `Meta.ordering = ("id",)`

There is deliberately **no** `topic` column: the content API can re-parent a block
to another Topic (`apps/content/services.py:495-496`), so a stored `(topic, block)`
pair could go stale. The Topic is always derived from `block.topic`, every
topic-scoped read filters on `block__topic` and `block__status=published`, and the
route rejects a URL topic that differs from `block.topic_id` with 404
`RESOURCE_NOT_FOUND`.

## FlashcardReview

One current scheduler row per user and flashcard. No review-event history.

| Field | Type | Rules |
|---|---|---|
| `user` | `FK(settings.AUTH_USER_MODEL)` | required, `CASCADE`, `related_name="flashcard_reviews"` |
| `flashcard` | `FK(content.Flashcard)` | required, `CASCADE`, `related_name="reviews"` |
| `interval_days` | `PositiveIntegerField` | default `0` |
| `repetitions` | `PositiveIntegerField` | default `0` |
| `last_reviewed_at` | `DateTimeField` | nullable |
| `next_review_at` | `DateTimeField` | nullable |
| `created_at` / `updated_at` | `DateTimeField` | `auto_now_add` / `auto_now` |

Constraints:

- `UniqueConstraint(fields=["user", "flashcard"], name="learning_flashcardreview_unique_user_flashcard")`
- `Index(fields=["user", "next_review_at"], name="learning_fcreview_due_idx")` (Django caps index names at 30 characters; `models.E034`)
- `Meta.ordering = ("id",)`

Schedule (settings value `LEARNING_FLASHCARD_INTERVALS`, default
`(1, 3, 7, 14, 30)` days). Let
`index_of(x) = intervals.index(x) if x in intervals else -1`:

- `know` → `index = min(index_of(interval_days) + 1, len(intervals) - 1)`;
  `repetitions += 1`. A first `know` (`interval_days=0`, so `index_of = -1`) lands
  on the first interval; a `know` at the last interval stays there.
- `repeat` → `index = 0`; `repetitions = 0`.
- `interval_days = intervals[index]`; `last_reviewed_at = now`;
  `next_review_at = now + interval_days`.

## QuizAttempt

| Field | Type | Rules |
|---|---|---|
| `user` | `FK(settings.AUTH_USER_MODEL)` | required, `CASCADE`, `related_name="quiz_attempts"` |
| `quiz` | `FK(content.Quiz)` | required, `CASCADE`, `related_name="attempts"` |
| `status` | `CharField(16, choices)` | `active` (default) \| `submitted` |
| `answers_state` | `JSONField` | `default=dict`; shape `{"selected_answer_ids": []}`; answer IDs only |
| `question_ids` | `JSONField` | `default=list`; question IDs frozen at attempt start |
| `results` | `JSONField` | `null=True, blank=True`; `null` while active, graded breakdown after submit |
| `score_percent` | `PositiveSmallIntegerField` | nullable until submitted |
| `started_at` | `DateTimeField` | `auto_now_add` |
| `submitted_at` | `DateTimeField` | nullable |
| `updated_at` | `DateTimeField` | `auto_now` |

Constraints:

- `UniqueConstraint(fields=["user", "quiz"], condition=Q(status="active"), name="learning_quizattempt_unique_active_user_quiz")`
- `CheckConstraint(status in ("active", "submitted"), name="learning_quizattempt_status_valid")`
- `CheckConstraint(score_percent is null or 0 <= score_percent <= 100, name="learning_quizattempt_score_bounds")`
- `Index(fields=["user", "quiz", "status"], name="learning_quizattempt_quiz_idx")` (30-character index-name limit)
- `Meta.ordering = ("id",)`

### Persisted shapes

```jsonc
// active
{
  "answers_state": {"selected_answer_ids": [12, 15]},
  "question_ids": [3, 4, 5],
  "results": null,
  "score_percent": null
}

// submitted (results frozen at submit)
{
  "answers_state": {"selected_answer_ids": [12, 15]},
  "question_ids": [3, 4, 5],
  "results": [
    {
      "question_id": 3,
      "selected_answer_ids": [12],
      "correct_answer_ids": [12, 14],
      "score_percent": 50
    }
  ],
  "score_percent": 83
}
```

`answers_state` holds answer IDs only, as the spec requires; the frozen question
set and the graded breakdown live in their own fields (decision record §Q2.1).
No question or answer text is ever copied into the attempt, and no correctness
value is exposed while the attempt is active.

### Grading policy

- The question set is frozen when the attempt starts (`question_ids`), so a
  question added later cannot change an in-flight attempt's denominator.
- Grading at submit uses the current `QuizAnswer.is_correct` values for the frozen
  questions. 004 guarantees that quiz child IDs are stable and never deleted, so
  a selected ID can never dangle.
- The graded `results` and `score_percent` are persisted at submit; a
  submitted attempt is immutable and its score is reproducible from the stored
  row alone.

### Scoring

Per question:

```text
max(0, (correct_selected - incorrect_selected) / correct_answer_count)
```

- `correct_selected` = selected answers that are correct;
- `incorrect_selected` = selected answers that are not correct;
- `correct_answer_count` = number of correct answers of the question;
- an unanswered question scores 0;
- a question with no correct answer scores 0 (defensive; the content API enforces
  at least one).

Quiz score = arithmetic mean of the per-question fractions over the frozen
question set, expressed as a percentage and rounded **once** with
`ROUND_HALF_UP`; `0` when the frozen set is empty. Arithmetic uses
`fractions.Fraction` internally, so no float drift can appear.

The stored top-level `score_percent` is **authoritative** and computed from the
exact fractions. Each `results[].score_percent` is the same value rounded with
`ROUND_HALF_UP` for display only, so the per-question values can differ from the
total by a rounding step and must never be averaged to reconstruct it.

No pass/fail flag is computed: the register states that no global pass percentage
is introduced (item 65) and the threshold is an open owner decision (decision
record, post-analysis correction 1).

## Derived values

| Value | Definition |
|---|---|
| `total_blocks` | number of published `ContentBlock` rows of the Topic (`content.selectors.topic_content_blocks(topic, preview_only=False)`) |
| `completed_blocks` | `UserTopicBlockProgress` rows with `is_complete=True` filtered on `block__topic=topic` and `block__status=published` (derived from the block side, never from a stored topic column) |
| `theory_percent` | `ROUND_HALF_UP(100 × completed_blocks / total_blocks)`; `0` when `total_blocks == 0` |
| `best_score_percent` | `Max(score_percent)` over the current user's `submitted` attempts of the quiz; `null` without one |

## Deletion matrix

| Source deletion | Learning rows removed | Mechanism |
|---|---|---|
| `User` (001 contract) | all four models | `ON DELETE CASCADE` on every `user` FK |
| `Topic` | `UserTopicProgress`, `UserTopicBlockProgress`, `FlashcardReview`, `QuizAttempt` | `CASCADE` on `topic`, and through the content cascade chain (`ContentBlock.topic`, `Flashcard.topic`, `Quiz.topic` are `CASCADE`) |
| `ContentBlock` | `UserTopicBlockProgress` | `CASCADE` on `block` |
| `Flashcard` | `FlashcardReview` | `CASCADE` on `flashcard` |
| `Quiz` | `QuizAttempt` | `CASCADE` on `quiz` |
| `Section`, `Subject` | none | `Topic.section` / `Section.subject` are `PROTECT`; no learning row references them |

`content` never imports `learning` and never calls a learning service; the
database cascade is the whole cross-domain contract (002 and 004 decisions).
No retention, tombstone, export or soft delete is added.

## Not modelled (deliberately)

- Review-event history (out of scope; FSRS and adaptive scheduling stay deferred).
- A stored best score (derived only).
- A `passed` flag and any pass threshold: register item 65 forbids introducing a
  global pass percentage, so the threshold is an open owner decision.
- `QuizAttemptAnswer` rows per answer (the compact JSON shapes above are the
  accepted MVP form).
- A Section-level progress entity (no Section exists inside a Topic).
- Automatic score-based topic completion (its threshold is an open owner
  decision; see the spec's `Out of scope`).
