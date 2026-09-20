"""Dashboard reads and aggregates for the learning API (feature 007)."""

from __future__ import annotations

from typing import Any

from django.db.models import Count, Exists, Max, OuterRef, Q
from django.utils import timezone

from apps.content.access import evaluate_topic_access
from apps.content.models import ContentBlock, Topic
from apps.learning.models import (
    FlashcardReview,
    QuizAttempt,
    UserTopicBlockProgress,
    UserTopicProgress,
)
from apps.learning.progress.selectors import theory_percent
from apps.subscriptions.policy import has_paid_content_entitlement


def get_user_dashboard(user) -> dict[str, Any]:
    """Build the aggregated dashboard payload for the authenticated user.

    Only accessible published topics with user learning activity are included.
    No N+1 queries: aggregates are performed in bounded set-based queries.
    """
    now = timezone.now()

    # 1. Base query for published topics accessible to the current user
    topics_qs = Topic.objects.filter(
        status=Topic.Status.PUBLISHED,
    ).select_related("section", "section__subject")

    if not has_paid_content_entitlement(user):
        topics_qs = topics_qs.exclude(access_level=Topic.AccessLevel.PAID)

    # 2. Filter topics that have any learning activity for this user
    user_progress_exists = UserTopicProgress.objects.filter(
        topic=OuterRef("pk"),
        user=user,
    ).filter(
        Q(
            status__in=[
                UserTopicProgress.Status.LEARNING,
                UserTopicProgress.Status.LEARNED,
            ]
        )
        | Q(last_opened_at__isnull=False)
        | Q(started_at__isnull=False)
        | Q(completed_at__isnull=False)
    )

    block_progress_exists = UserTopicBlockProgress.objects.filter(
        block__topic=OuterRef("pk"),
        block__status=ContentBlock.Status.PUBLISHED,
        user=user,
        is_complete=True,
    )

    flashcard_review_exists = FlashcardReview.objects.filter(
        flashcard__topic=OuterRef("pk"),
        user=user,
    )

    quiz_attempt_exists = QuizAttempt.objects.filter(
        quiz__topic=OuterRef("pk"),
        user=user,
    )

    started_filter = (
        Q(Exists(user_progress_exists))
        | Q(Exists(block_progress_exists))
        | Q(Exists(flashcard_review_exists))
        | Q(Exists(quiz_attempt_exists))
    )

    candidate_topics = list(topics_qs.filter(started_filter))

    # Defensive check: re-verify topic access policy for each candidate topic
    started_topics = [
        t for t in candidate_topics if evaluate_topic_access(t, user).full_access
    ]

    if not started_topics:
        return {
            "summary": {
                "started_topics_count": 0,
                "completed_theory_topics_count": 0,
                "flashcards_due_count": 0,
                "quizzes_attempted_count": 0,
            },
            "topics": [],
        }

    topic_ids = [t.pk for t in started_topics]

    # 3. Bounded aggregate queries across started topics
    # A. User topic progress rows
    progress_rows = UserTopicProgress.objects.filter(
        user=user,
        topic_id__in=topic_ids,
    )
    progress_by_topic = {row.topic_id: row for row in progress_rows}

    # B. Published content blocks per topic (total)
    total_blocks_rows = (
        ContentBlock.objects.filter(
            topic_id__in=topic_ids,
            status=ContentBlock.Status.PUBLISHED,
        )
        .values("topic_id")
        .annotate(total=Count("id"))
    )
    total_blocks_by_topic = {row["topic_id"]: row["total"] for row in total_blocks_rows}

    # C. Completed blocks and timestamps per topic
    completed_blocks_rows = (
        UserTopicBlockProgress.objects.filter(
            user=user,
            block__topic_id__in=topic_ids,
            block__status=ContentBlock.Status.PUBLISHED,
            is_complete=True,
        )
        .values("block__topic_id")
        .annotate(
            completed=Count("id"),
            last_completed=Max("completed_at"),
            last_updated=Max("updated_at"),
        )
    )
    completed_blocks_by_topic = {
        row["block__topic_id"]: row for row in completed_blocks_rows
    }

    # D. Flashcards due count and timestamps per topic
    flashcard_rows = (
        FlashcardReview.objects.filter(
            user=user,
            flashcard__topic_id__in=topic_ids,
        )
        .values("flashcard__topic_id")
        .annotate(
            due_count=Count(
                "id",
                filter=Q(
                    next_review_at__lte=now,
                    flashcard__topic__status=Topic.Status.PUBLISHED,
                ),
            ),
            last_reviewed=Max("last_reviewed_at"),
            last_updated=Max("updated_at"),
            last_created=Max("created_at"),
        )
    )
    flashcards_by_topic = {row["flashcard__topic_id"]: row for row in flashcard_rows}

    # E. Quiz attempt aggregates per topic
    quiz_attempt_rows = (
        QuizAttempt.objects.filter(
            user=user,
            quiz__topic_id__in=topic_ids,
        )
        .values("quiz__topic_id")
        .annotate(
            attempt_count=Count("id"),
            best_score=Max(
                "score_percent",
                filter=Q(status=QuizAttempt.Status.SUBMITTED),
            ),
            last_started=Max("started_at"),
            last_submitted=Max("submitted_at"),
            last_updated=Max("updated_at"),
        )
    )
    quizzes_by_topic = {row["quiz__topic_id"]: row for row in quiz_attempt_rows}

    # F. Unique quizzes attempted across started topics
    quizzes_attempted_count = (
        QuizAttempt.objects.filter(
            user=user,
            quiz__topic_id__in=topic_ids,
        )
        .values("quiz_id")
        .distinct()
        .count()
    )

    # 4. Build topic item payload
    topics_data = []
    for topic in started_topics:
        t_id = topic.pk

        # Theory
        p_row = progress_by_topic.get(t_id)
        theory_status = p_row.status if p_row else UserTopicProgress.Status.NOT_STARTED
        total_blocks = total_blocks_by_topic.get(t_id, 0)
        cb_data = completed_blocks_by_topic.get(t_id)
        completed_blocks_count = cb_data["completed"] if cb_data else 0
        progress_pct = theory_percent(completed_blocks_count, total_blocks)

        # Flashcards
        fc_data = flashcards_by_topic.get(t_id)
        fc_due_count = fc_data["due_count"] if fc_data else 0

        # Quiz
        qz_data = quizzes_by_topic.get(t_id)
        if qz_data and qz_data["attempt_count"] > 0:
            quiz_attempted = True
            best_score = qz_data["best_score"]
        else:
            quiz_attempted = False
            best_score = None

        # Activity timestamps
        timestamps = []
        if p_row:
            for ts in (
                p_row.updated_at,
                p_row.last_opened_at,
                p_row.completed_at,
                p_row.started_at,
            ):
                if ts is not None:
                    timestamps.append(ts)
        if cb_data:
            for ts in (cb_data["last_completed"], cb_data["last_updated"]):
                if ts is not None:
                    timestamps.append(ts)
        if fc_data:
            for ts in (
                fc_data["last_reviewed"],
                fc_data["last_updated"],
                fc_data["last_created"],
            ):
                if ts is not None:
                    timestamps.append(ts)
        if qz_data:
            for ts in (
                qz_data["last_submitted"],
                qz_data["last_started"],
                qz_data["last_updated"],
            ):
                if ts is not None:
                    timestamps.append(ts)

        last_activity_at = max(timestamps) if timestamps else topic.updated_at

        topics_data.append(
            {
                "id": topic.pk,
                "title": topic.title,
                "subject": {
                    "id": topic.section.subject.pk,
                    "title": topic.section.subject.title,
                },
                "section": {
                    "id": topic.section.pk,
                    "title": topic.section.title,
                },
                "theory": {
                    "status": theory_status,
                    "progress_percent": progress_pct,
                },
                "flashcards": {
                    "due_count": fc_due_count,
                },
                "quiz": {
                    "attempted": quiz_attempted,
                    "best_score_percent": best_score,
                },
                "last_activity_at": last_activity_at,
            }
        )

    # 5. Sort topics by last_activity_at desc
    topics_data.sort(
        key=lambda item: (item["last_activity_at"], item["id"]),
        reverse=True,
    )

    # 6. Summary metrics
    completed_theory_count = sum(
        1
        for item in topics_data
        if item["theory"]["status"] == UserTopicProgress.Status.LEARNED
    )
    total_flashcards_due = sum(item["flashcards"]["due_count"] for item in topics_data)

    return {
        "summary": {
            "started_topics_count": len(topics_data),
            "completed_theory_topics_count": completed_theory_count,
            "flashcards_due_count": total_flashcards_due,
            "quizzes_attempted_count": quizzes_attempted_count,
        },
        "topics": topics_data,
    }
