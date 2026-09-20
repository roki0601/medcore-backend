"""Comprehensive test suite for the learning dashboard API (BE-007)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.content.models import Topic
from apps.learning.models import (
    FlashcardReview,
    QuizAttempt,
    UserTopicBlockProgress,
    UserTopicProgress,
)
from apps.learning.progress.services import (
    complete_topic_block,
    mark_topic_learned,
    open_topic,
)
from apps.subscriptions.models import Plan, Subscription


@pytest.fixture
def plan(db):
    return Plan.objects.create(
        code="monthly",
        title="Monthly Plan",
        price_rub=990,
        duration_days=30,
        is_active=True,
    )


@pytest.mark.django_db
def test_dashboard_anonymous_denied(api_client):
    """1. Anonymous user receives 401 AUTHENTICATION_REQUIRED."""
    response = api_client.get("/api/v1/dashboard/")
    assert response.status_code == 401
    payload = response.json()
    assert payload["code"] == "AUTHENTICATION_REQUIRED"
    assert "detail" in payload
    assert "fields" in payload


@pytest.mark.django_db
def test_dashboard_empty_for_user_without_activity(
    api_client, authenticate, make_user, demo_topic
):
    """2. User with no learning activity gets zeros and empty topics list."""
    user = make_user(username="newbie")
    client = authenticate(api_client, user)

    response = client.get("/api/v1/dashboard/")
    assert response.status_code == 200
    assert response.json() == {
        "summary": {
            "started_topics_count": 0,
            "completed_theory_topics_count": 0,
            "flashcards_due_count": 0,
            "quizzes_attempted_count": 0,
        },
        "topics": [],
    }


@pytest.mark.django_db
@pytest.mark.parametrize("activity_type", ["theory", "flashcard", "quiz"])
def test_single_activity_type_makes_topic_started(
    api_client,
    authenticate,
    make_user,
    make_topic,
    make_block,
    make_flashcard,
    make_quiz,
    activity_type,
):
    """3, 4, 5. Each single activity type makes the topic appear as started."""
    user = make_user(username="learner")
    client = authenticate(api_client, user)
    topic = make_topic(title="Microbiology")

    if activity_type == "theory":
        block = make_block(topic)
        complete_topic_block(user, topic, block.pk)
    elif activity_type == "flashcard":
        card = make_flashcard(topic)
        FlashcardReview.objects.create(
            user=user,
            flashcard=card,
            next_review_at=timezone.now() + timedelta(days=1),
        )
    elif activity_type == "quiz":
        quiz = make_quiz(topic)
        QuizAttempt.objects.create(
            user=user,
            quiz=quiz,
            status=QuizAttempt.Status.ACTIVE,
        )

    response = client.get("/api/v1/dashboard/")
    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["started_topics_count"] == 1
    assert len(data["topics"]) == 1
    assert data["topics"][0]["id"] == topic.pk
    assert data["topics"][0]["title"] == "Microbiology"
    assert data["topics"][0]["subject"]["id"] == topic.section.subject.pk
    assert data["topics"][0]["subject"]["title"] == topic.section.subject.title
    assert data["topics"][0]["section"]["id"] == topic.section.pk
    assert data["topics"][0]["section"]["title"] == topic.section.title


@pytest.mark.django_db
def test_topic_with_multiple_activities_counted_once(
    api_client,
    authenticate,
    make_user,
    make_topic,
    make_block,
    make_flashcard,
    make_quiz,
):
    """6. A topic with theory, flashcard and quiz activities is counted only once."""
    user = make_user(username="multi_activity_user")
    client = authenticate(api_client, user)
    topic = make_topic(title="Immunology")

    block = make_block(topic)
    complete_topic_block(user, topic, block.pk)

    card = make_flashcard(topic)
    FlashcardReview.objects.create(
        user=user,
        flashcard=card,
        next_review_at=timezone.now() - timedelta(hours=1),
    )

    quiz = make_quiz(topic)
    QuizAttempt.objects.create(
        user=user,
        quiz=quiz,
        status=QuizAttempt.Status.SUBMITTED,
        score_percent=85,
    )

    response = client.get("/api/v1/dashboard/")
    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["started_topics_count"] == 1
    assert len(data["topics"]) == 1
    item = data["topics"][0]
    assert item["id"] == topic.pk
    assert item["flashcards"]["due_count"] == 1
    assert item["quiz"]["attempted"] is True
    assert item["quiz"]["best_score_percent"] == 85


@pytest.mark.django_db
def test_summary_counters_and_quiz_scores(
    api_client,
    authenticate,
    make_user,
    make_topic,
    make_block,
    make_flashcard,
    make_quiz,
):
    """7, 8, 9, 10. Summary counters, submitted vs active score, and due cards."""
    user = make_user(username="summary_tester")
    client = authenticate(api_client, user)

    # Topic 1: learned theory, 2 due cards, 1 quiz with active + 2 submitted attempts
    t1 = make_topic(title="Topic 1")
    make_block(t1)
    open_topic(user, t1)
    mark_topic_learned(user, t1)

    c1 = make_flashcard(t1)
    c2 = make_flashcard(t1)
    now = timezone.now()
    FlashcardReview.objects.create(
        user=user, flashcard=c1, next_review_at=now - timedelta(hours=2)
    )
    FlashcardReview.objects.create(
        user=user, flashcard=c2, next_review_at=now - timedelta(minutes=5)
    )

    q1 = make_quiz(t1)
    QuizAttempt.objects.create(
        user=user, quiz=q1, status=QuizAttempt.Status.SUBMITTED, score_percent=50
    )
    QuizAttempt.objects.create(
        user=user, quiz=q1, status=QuizAttempt.Status.SUBMITTED, score_percent=90
    )
    QuizAttempt.objects.create(
        user=user, quiz=q1, status=QuizAttempt.Status.ACTIVE, score_percent=None
    )

    # Topic 2: in-progress theory, 1 future card, 1 quiz with active-only attempt
    t2 = make_topic(title="Topic 2")
    b2 = make_block(t2)
    make_block(t2)  # second block uncompleted -> 50%
    complete_topic_block(user, t2, b2.pk)

    c3 = make_flashcard(t2)
    FlashcardReview.objects.create(
        user=user, flashcard=c3, next_review_at=now + timedelta(days=2)
    )

    q2 = make_quiz(t2)
    QuizAttempt.objects.create(
        user=user, quiz=q2, status=QuizAttempt.Status.ACTIVE, score_percent=None
    )

    # Multiple attempts on same quiz (q2) should count as 1 unique quiz attempt
    response = client.get("/api/v1/dashboard/")
    assert response.status_code == 200
    data = response.json()

    # Summary checks
    assert data["summary"]["started_topics_count"] == 2
    assert data["summary"]["completed_theory_topics_count"] == 1
    assert data["summary"]["flashcards_due_count"] == 2
    assert data["summary"]["quizzes_attempted_count"] == 2

    # Topic items check
    topics_by_id = {t["id"]: t for t in data["topics"]}

    # Topic 1: best submitted score is 90
    t1_data = topics_by_id[t1.pk]
    assert t1_data["theory"]["status"] == UserTopicProgress.Status.LEARNED
    assert t1_data["flashcards"]["due_count"] == 2
    assert t1_data["quiz"]["attempted"] is True
    assert t1_data["quiz"]["best_score_percent"] == 90

    # Topic 2: only active attempt -> best_score_percent is None, attempted is True
    t2_data = topics_by_id[t2.pk]
    assert t2_data["theory"]["status"] == UserTopicProgress.Status.LEARNING
    assert t2_data["theory"]["progress_percent"] == 50
    assert t2_data["flashcards"]["due_count"] == 0  # not due yet
    assert t2_data["quiz"]["attempted"] is True
    assert t2_data["quiz"]["best_score_percent"] is None


@pytest.mark.django_db
def test_topics_sorted_by_last_activity_at_desc(
    api_client,
    authenticate,
    make_user,
    make_topic,
    make_block,
    make_quiz,
):
    """11. Topics are sorted by last_activity_at DESC."""
    user = make_user(username="sorting_user")
    client = authenticate(api_client, user)
    now = timezone.now()

    # Topic A: activity 3 days ago
    t_a = make_topic(title="Topic A")
    UserTopicProgress.objects.create(
        user=user,
        topic=t_a,
        status=UserTopicProgress.Status.LEARNING,
        last_opened_at=now - timedelta(days=3),
    )

    # Topic B: activity 1 day ago
    t_b = make_topic(title="Topic B")
    q_b = make_quiz(t_b)
    QuizAttempt.objects.create(
        user=user,
        quiz=q_b,
        status=QuizAttempt.Status.SUBMITTED,
        score_percent=80,
        submitted_at=now - timedelta(days=1),
    )

    # Topic C: activity 5 minutes ago
    t_c = make_topic(title="Topic C")
    b_c = make_block(t_c)
    UserTopicBlockProgress.objects.create(
        user=user,
        block=b_c,
        is_complete=True,
        completed_at=now - timedelta(minutes=5),
    )

    response = client.get("/api/v1/dashboard/")
    assert response.status_code == 200
    topics = response.json()["topics"]
    assert len(topics) == 3
    assert [t["id"] for t in topics] == [t_c.pk, t_b.pk, t_a.pk]


@pytest.mark.django_db
def test_paid_topic_hidden_without_entitlement(
    api_client,
    authenticate,
    make_user,
    make_topic,
    make_block,
    plan,
):
    """12. Inaccessible paid Topic does not leak when entitlement expires."""
    user = make_user(username="subscriber")
    client = authenticate(api_client, user)
    now = timezone.now()

    # Create paid topic and record progress
    paid_top = make_topic(title="Advanced Surgery", access_level=Topic.AccessLevel.PAID)
    block = make_block(paid_top)
    open_topic(user, paid_top)
    complete_topic_block(user, paid_top, block.pk)

    # Also create a demo topic with activity
    demo_top = make_topic(title="Basic First Aid", access_level=Topic.AccessLevel.DEMO)
    open_topic(user, demo_top)

    # Case A: User has active subscription -> both topics appear
    sub = Subscription.objects.create(
        user=user,
        plan=plan,
        status=Subscription.Status.ACTIVE,
        starts_at=now - timedelta(days=1),
        expires_at=now + timedelta(days=29),
    )
    res_entitled = client.get("/api/v1/dashboard/")
    assert res_entitled.status_code == 200
    entitled_topics = {t["id"] for t in res_entitled.json()["topics"]}
    assert paid_top.pk in entitled_topics
    assert demo_top.pk in entitled_topics
    assert res_entitled.json()["summary"]["started_topics_count"] == 2

    # Case B: Subscription expired -> paid topic hidden completely from dashboard
    sub.expires_at = now - timedelta(hours=1)
    sub.save()

    res_expired = client.get("/api/v1/dashboard/")
    assert res_expired.status_code == 200
    data_expired = res_expired.json()
    expired_topic_ids = [t["id"] for t in data_expired["topics"]]
    assert paid_top.pk not in expired_topic_ids
    assert demo_top.pk in expired_topic_ids
    assert data_expired["summary"]["started_topics_count"] == 1


@pytest.mark.django_db
def test_other_user_learning_state_does_not_leak(
    api_client,
    authenticate,
    make_user,
    make_topic,
    make_block,
    make_flashcard,
    make_quiz,
):
    """13. Another user's learning state does not appear on current user's dashboard."""
    user_a = make_user(username="alice")
    user_b = make_user(username="bob")

    topic_a = make_topic(title="Alice Only Topic")
    b_a = make_block(topic_a)
    complete_topic_block(user_a, topic_a, b_a.pk)

    topic_shared = make_topic(title="Shared Topic")
    fc = make_flashcard(topic_shared)
    # Alice reviews card, Bob does not
    FlashcardReview.objects.create(
        user=user_a,
        flashcard=fc,
        next_review_at=timezone.now() - timedelta(hours=1),
    )

    # Bob only has quiz attempt on topic_shared
    quiz = make_quiz(topic_shared)
    QuizAttempt.objects.create(
        user=user_b,
        quiz=quiz,
        status=QuizAttempt.Status.SUBMITTED,
        score_percent=70,
    )

    # Check Bob's dashboard
    client_b = authenticate(api_client, user_b)
    response = client_b.get("/api/v1/dashboard/")
    assert response.status_code == 200
    data = response.json()

    # Bob should only see topic_shared, NOT topic_a
    assert data["summary"]["started_topics_count"] == 1
    assert data["summary"]["flashcards_due_count"] == 0  # Alice's review is not Bob's
    assert len(data["topics"]) == 1
    assert data["topics"][0]["id"] == topic_shared.pk
    assert data["topics"][0]["flashcards"]["due_count"] == 0
    assert data["topics"][0]["quiz"]["attempted"] is True
    assert data["topics"][0]["quiz"]["best_score_percent"] == 70


@pytest.mark.django_db
def test_dashboard_query_count_is_bounded_no_n_plus_1(
    api_client,
    authenticate,
    make_user,
    make_topic,
    make_block,
    make_flashcard,
    make_quiz,
    django_assert_num_queries,
):
    """14. Endpoint has bounded query count: does not grow linearly with topic count."""
    user = make_user(username="perf_tester")
    client = authenticate(api_client, user)

    # Create 1 topic with activity
    t1 = make_topic(title="Perf Topic 1")
    b1 = make_block(t1)
    complete_topic_block(user, t1, b1.pk)

    # First request establishes baseline query count (and caches auth/session)
    client.get("/api/v1/dashboard/")

    # 1 topic: 9 queries (1 auth, 1 entitlement, 7 aggregates)
    with django_assert_num_queries(9):
        r1 = client.get("/api/v1/dashboard/")
    assert r1.status_code == 200
    assert len(r1.json()["topics"]) == 1

    # Now add 4 more started topics with various activities
    for i in range(2, 6):
        top = make_topic(title=f"Perf Topic {i}")
        b = make_block(top)
        complete_topic_block(user, top, b.pk)
        fc = make_flashcard(top)
        FlashcardReview.objects.create(
            user=user,
            flashcard=fc,
            next_review_at=timezone.now() - timedelta(hours=1),
        )
        qz = make_quiz(top)
        QuizAttempt.objects.create(
            user=user,
            quiz=qz,
            status=QuizAttempt.Status.SUBMITTED,
            score_percent=80,
        )

    # 5 topics: query count remains exactly 9 (O(1) bounded queries)
    with django_assert_num_queries(9):
        r2 = client.get("/api/v1/dashboard/")
    assert r2.status_code == 200
    assert len(r2.json()["topics"]) == 5


@pytest.mark.django_db
def test_paid_topics_query_count_bounded_no_n_plus_1(
    api_client,
    authenticate,
    make_user,
    make_topic,
    make_block,
    make_flashcard,
    make_quiz,
    plan,
    django_assert_num_queries,
):
    """Regression test: query count does not grow with multiple paid topics."""
    user = make_user(username="paid_perf_tester")
    client = authenticate(api_client, user)
    now = timezone.now()

    # Active subscription gives paid entitlement
    Subscription.objects.create(
        user=user,
        plan=plan,
        status=Subscription.Status.ACTIVE,
        starts_at=now - timedelta(days=1),
        expires_at=now + timedelta(days=29),
    )

    # 1 paid started topic
    t1 = make_topic(title="Paid Topic 1", access_level=Topic.AccessLevel.PAID)
    b1 = make_block(t1)
    complete_topic_block(user, t1, b1.pk)

    # Warm up client / session cache
    client.get("/api/v1/dashboard/")

    # 1 paid topic: exactly 9 queries
    with django_assert_num_queries(9):
        r1 = client.get("/api/v1/dashboard/")
    assert r1.status_code == 200
    assert len(r1.json()["topics"]) == 1

    # Add 4 more paid started topics (total 5 paid started topics)
    for i in range(2, 6):
        top = make_topic(
            title=f"Paid Topic {i}",
            access_level=Topic.AccessLevel.PAID,
        )
        b = make_block(top)
        complete_topic_block(user, top, b.pk)
        fc = make_flashcard(top)
        FlashcardReview.objects.create(
            user=user,
            flashcard=fc,
            next_review_at=timezone.now() - timedelta(hours=1),
        )
        qz = make_quiz(top)
        QuizAttempt.objects.create(
            user=user,
            quiz=qz,
            status=QuizAttempt.Status.SUBMITTED,
            score_percent=85,
        )

    # 5 paid topics: query count must remain exactly 9 (no N+1 per paid topic)
    with django_assert_num_queries(9):
        r2 = client.get("/api/v1/dashboard/")
    assert r2.status_code == 200
    assert len(r2.json()["topics"]) == 5


@pytest.mark.django_db
def test_mixed_access_levels_active_entitlement(
    api_client,
    authenticate,
    make_user,
    make_topic,
    make_block,
    plan,
    django_assert_num_queries,
):
    """Mixed demo, free, paid topics under active entitlement all appear in O(1)."""
    user = make_user(username="mixed_tester")
    client = authenticate(api_client, user)
    now = timezone.now()

    Subscription.objects.create(
        user=user,
        plan=plan,
        status=Subscription.Status.ACTIVE,
        starts_at=now - timedelta(days=1),
        expires_at=now + timedelta(days=29),
    )

    t_demo = make_topic(title="Demo Topic", access_level=Topic.AccessLevel.DEMO)
    b_demo = make_block(t_demo)
    complete_topic_block(user, t_demo, b_demo.pk)

    t_free = make_topic(title="Free Topic", access_level=Topic.AccessLevel.FREE)
    b_free = make_block(t_free)
    complete_topic_block(user, t_free, b_free.pk)

    t_paid = make_topic(title="Paid Topic", access_level=Topic.AccessLevel.PAID)
    b_paid = make_block(t_paid)
    complete_topic_block(user, t_paid, b_paid.pk)

    client.get("/api/v1/dashboard/")

    with django_assert_num_queries(9):
        res = client.get("/api/v1/dashboard/")
    assert res.status_code == 200
    data = res.json()
    assert data["summary"]["started_topics_count"] == 3
    returned_ids = {t["id"] for t in data["topics"]}
    assert returned_ids == {t_demo.pk, t_free.pk, t_paid.pk}
