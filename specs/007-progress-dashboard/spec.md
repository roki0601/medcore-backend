# Feature 007 — Progress/dashboard aggregate API

- Status: MERGED (PR #15)
- Date: 2026-09-20
- Owning Django app: `apps.learning`
- Consumers: Authenticated web/mobile dashboard clients

## 1. Summary and Business Goal

MedCore backend previously exposed learning state strictly per topic via `GET /api/v1/topics/{topic_id}/progress/`.
As the catalog expands, fetching personal learning state individually generates excessive frontend network requests (N queries).
Feature BE-007 introduces an authenticated, user-wide dashboard aggregate endpoint:
`GET /api/v1/dashboard/`

This endpoint returns a consolidated summary and a list of all topics where the user has active learning engagement, without loading or returning untouched catalog topics.

## 2. Architecture and Domain Boundaries

1. **Owning App**: `apps.learning`
   - Located in `apps/learning/dashboard/`.
   - Read-model / aggregate layer using selectors; no unnecessary service layer or mutations.
2. **Started Topic Definition**:
   - A topic is considered "started" if there is at least one persistent learning state for the user:
     - `UserTopicProgress` with `status in ('learning', 'learned')` or timestamps (`last_opened_at`, `started_at`, `completed_at`);
     - `UserTopicBlockProgress` with `is_complete=True`;
     - `FlashcardReview` row;
     - `QuizAttempt` row.
   - Topics with no user activity are excluded from both summary counters and the topics list.
3. **Access Control & Paywall Security**:
   - Re-evaluates topic access via `evaluate_topic_access(topic, user)`.
   - If a user previously started a `paid` topic but their subscription expired (or they lack entitlement), that topic and its learning metrics are excluded from the response.
4. **No Synthetic Overall Progress**:
   - There is no combined percentage across theory, flashcards, and quizzes.
   - Theory progress percentage uses the canonical `theory_percent` formula from `apps.learning.progress.selectors`.
5. **No Pagination for MVP**:
   - DRF default pagination is explicitly disabled (`pagination_class = None`).
   - The payload returns all started topics for the user.
6. **Performance & Query Bounding**:
   - Zero N+1 query patterns.
   - All aggregations are performed via set-based queries using `OuterRef`, `Exists`, `Count`, `Max`, and `FILTER (WHERE ...)`.
   - Query count is strictly bounded (O(1) relative to topic count).

## 3. Semantics and Metrics

### 3.1. Summary Counters
- `started_topics_count`: Count of unique accessible started topics.
- `completed_theory_topics_count`: Count of started topics with `status == "learned"`.
- `flashcards_due_count`: Total flashcards due right now (`next_review_at <= now`) across all accessible started topics.
- `quizzes_attempted_count`: Count of unique quizzes with at least one attempt created by the user across accessible started topics.

### 3.2. Topic Item Metrics
- `basic_metadata`: `id`, `title`, `subject` (`id`, `title`), `section` (`id`, `title`).
- `theory`:
  - `status`: `"not_started" | "learning" | "learned"`.
  - `progress_percent`: integer 0–100.
- `flashcards`:
  - `due_count`: integer >= 0.
- `quiz`:
  - `attempted`: boolean.
  - `best_score_percent`: integer (0–100) or null. Derived exclusively from submitted attempts; active attempts do not count toward score.
- `last_activity_at`: Maximum of relevant timestamps across theory progress, block completions, flashcard reviews, and quiz attempts. Topics are sorted `last_activity_at DESC`.

## 4. Testing & Verification

The feature includes:
- Unit & integration tests in `apps/learning/tests/test_dashboard_api.py`:
  - 401 for anonymous requests.
  - Empty response (zeros + empty list) for users without activity.
  - Verification that theory-only, flashcard-only, or quiz-only activity marks a topic started.
  - De-duplication across multiple activity types on a single topic.
  - Correctness of summary counters and quiz best score calculation.
  - Active attempts not counting toward score.
  - Due flashcards scheduler logic validation.
  - Ordering by `last_activity_at DESC`.
  - Paywall containment: paid topics hidden when entitlement expires.
  - Isolation: no leakage of another user's activity.
  - Query count assertion proving bounded O(1) query execution.
- OpenAPI schema contract validation in `apps/learning/tests/test_openapi.py` and `apps/common/tests/test_openapi_contract.py`.
