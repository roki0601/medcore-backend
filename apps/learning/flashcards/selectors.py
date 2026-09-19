"""Flashcard reads for the learning API (feature 003).

The topic list, the per-card lookup and the due selector all re-check the
``content`` access decision per Topic, so an inaccessible (for example ``paid``
without entitlement) or unpublished Topic never contributes a row.
"""

from __future__ import annotations

from datetime import datetime

from django.db.models import QuerySet

from apps.content.access import evaluate_topic_access
from apps.content.models import Flashcard, Topic
from apps.learning.models import FlashcardReview


def topic_flashcards(topic: Topic) -> QuerySet[Flashcard]:
    """Every flashcard of one Topic in ``(position, id)`` order."""

    return Flashcard.objects.filter(topic=topic).order_by("position", "id")


def reviews_by_flashcard(user, flashcard_ids: list[int]) -> dict[int, FlashcardReview]:
    """The user's current review rows keyed by flashcard id."""

    if not flashcard_ids:
        return {}
    rows = FlashcardReview.objects.filter(user=user, flashcard_id__in=flashcard_ids)
    return {row.flashcard_id: row for row in rows}


def due_flashcard_reviews(user, *, now: datetime) -> list[FlashcardReview]:
    """Review rows due at ``now`` on published, accessible Topics.

    Ordered by ``(next_review_at, id)``. A never-reviewed card has no row and is
    therefore absent; a future ``next_review_at``, an unpublished Topic and a
    Topic the user cannot access are all excluded.
    """

    rows = (
        FlashcardReview.objects.filter(
            user=user,
            next_review_at__lte=now,
            flashcard__topic__status=Topic.Status.PUBLISHED,
        )
        .select_related("flashcard", "flashcard__topic")
        .order_by("next_review_at", "id")
    )
    accessible: dict[int, bool] = {}
    due: list[FlashcardReview] = []
    for row in rows:
        topic_id = row.flashcard.topic_id
        allowed = accessible.get(topic_id)
        if allowed is None:
            allowed = evaluate_topic_access(row.flashcard.topic, user).full_access
            accessible[topic_id] = allowed
        if allowed:
            due.append(row)
    return due
