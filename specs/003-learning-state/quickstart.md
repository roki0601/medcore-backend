# Quickstart: Learning state, flashcard review and quizzes

**Feature**: `003-learning-state`
**Prerequisites**: PostgreSQL and Redis reachable with the project `.env`; `uv`
installed; migrations applied.

## Setup

```bash
cd /home/roki/dev/medcore/medcore-backend
uv run python manage.py migrate
uv run python manage.py runserver 8000
```

Seed a published demo topic with two theory blocks, one flashcard and one quiz,
and mint a user access token (no secrets are printed):

```bash
uv run python manage.py shell -c "
from apps.content.models import ContentBlockType
from apps.content.services import save_flashcard, save_quiz, save_section, save_subject, save_topic
from apps.users.models import User
from rest_framework_simplejwt.tokens import RefreshToken

s = save_subject(title='Pharmacology')
sec = save_section(s, title='Antibiotics')
topic = save_topic(sec, title='Beta-lactams', status='published', access_level='demo')
markdown = ContentBlockType.objects.get(key='markdown')
for body in ('Short answer', 'Must know'):
    from apps.content.services import save_content_block
    save_content_block(topic, block_type_key=markdown.key, markdown_body=body, status='published')
save_flashcard(topic, question='Which ring is essential?', answer='Beta-lactam ring')
save_quiz(topic, title='Beta-lactams', questions=[{'text': 'Pick the penicillins', 'answers': [
    {'text': 'Ampicillin', 'is_correct': True}, {'text': 'Erythromycin', 'is_correct': False}]}])
user, _ = User.objects.get_or_create(username='smoke', defaults={'role': 'user'})
refresh = RefreshToken.for_user(user); refresh['auth_version'] = user.auth_version
print('TOPIC', topic.id); print('TOKEN', refresh.access_token)
"
```

Use `T=<TOKEN>` in `Authorization: Bearer $T` and `H='Content-Type: application/json'`.

## Smoke sequence

1. `GET /api/v1/topics/{topic}/progress/` **without** a token → 401
   `AUTHENTICATION_REQUIRED`; **with** `T` → 200, `status=not_started`,
   `theory_percent=0`, `completed_blocks=0`, `total_blocks=2`, `null` timestamps.
   Repeat the authenticated `GET` and confirm in the shell that
   `UserTopicProgress.objects.count()` is still 0 (`GET` never writes).
2. `POST /api/v1/topics/{topic}/blocks/{block_a}/complete/` → 201; repeat the same
   request → 200 and no duplicate row; `GET` progress → `status=learning`,
   `theory_percent=50`, `completed_blocks=1`.
3. `PATCH /api/v1/topics/{topic}/progress/` `{"opened": true}` → 200 with
   `last_opened_at`; `PATCH {"status": "learned"}` → 200 `status=learned`,
   `completed_at` set. Complete `{block_b}` → 200 and `status` stays `learned`.
4. `PATCH /api/v1/topics/{topic}/progress/` with `{"unexpected": 1}` → 422
   `VALIDATION_ERROR`; `POST .../blocks/{block_of_another_topic}/complete/` → 404
   `RESOURCE_NOT_FOUND`.
5. `GET /api/v1/topics/{topic}/flashcards/` → 200 with `review: null`.
   `POST /api/v1/flashcards/{card}/review/` `{"action": "know"}` → 201,
   `interval_days=1`; the same request again → 200, `interval_days=3`;
   `{"action": "repeat"}` → 200, `interval_days=1`, `repetitions=0`;
   `{"action": "later"}` → 422 `VALIDATION_ERROR`.
6. `GET /api/v1/flashcards/review-due/` → 200 without the card just reviewed
   (`next_review_at` is in the future); `GET /api/v1/flashcards/{card}/` → 200 with
   the current `review`.
7. `GET /api/v1/quizzes/{quiz}/` → 200 with `question_count=1`,
   `best_score_percent=null`, and **no** `is_correct` anywhere in `questions`.
   `POST /api/v1/quizzes/{quiz}/attempts/` → 201 with `question_ids`,
   `selected_answer_ids=[]`, `results=null`; repeat → 200 with the same attempt id.
8. `PATCH /api/v1/quiz-attempts/{attempt}/` `{"selected_answer_ids": [correct]}`
   → 200; `GET` the attempt → `questions` still without `is_correct`;
   `PATCH` with an answer of another quiz → 422 `INVALID_ANSWER`.
9. `POST /api/v1/quiz-attempts/{attempt}/submit/` → 200 `score_percent=100` with
   the frozen per-question `results` (no `passed` field exists);
   `PATCH`/`submit` again → 409 `ATTEMPT_ALREADY_SUBMITTED`.
10. `POST /api/v1/quizzes/{quiz}/attempts/` again → 201, a second attempt; the
    first attempt's stored score is unchanged. `GET /api/v1/quizzes/{quiz}/` →
    `best_score_percent=100`. Then flip the correct answer's `is_correct` through
    the content API and start a third attempt: its submit grades against the new
    value, while the earlier attempts keep their stored scores.
11. `GET /api/v1/topics/{paid_topic}/progress/` → 403
    `TOPIC_ENTITLEMENT_REQUIRED`; `GET /api/v1/topics/{draft_topic}/progress/` →
    404 `RESOURCE_NOT_FOUND`; another user's `GET /api/v1/quiz-attempts/{id}/` →
    404 `RESOURCE_NOT_FOUND`.
12. `GET /api/v1/schema/` contains all eleven learning paths (with the local
    `OPENAPI_PUBLIC=True` default; in production the schema needs an admin).
13. Repeated review/attempt requests beyond their scope → 429 `THROTTLED`.
14. Delete the Topic → its `UserTopicProgress`, `UserTopicBlockProgress`,
    `FlashcardReview` and `QuizAttempt` rows are gone; delete the User → the same
    rows disappear through the cascade.

## Expected result

All checks pass. No learning response contains `is_correct` before a submit, no
learning route creates state for an anonymous request, and every learning row is
removed by the database cascade when its User or content object is deleted.
