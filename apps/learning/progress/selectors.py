"""Derived topic-progress reads for the learning API (feature 003).

The snapshot is derived on every request: nothing about ``theory_percent`` or
the block counts is stored. A completed row counts only while its block still
belongs to the topic and is published, so a content re-parenting or unpublishing
cannot leave a stale count behind.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django.db.models import QuerySet

from apps.content.models import ContentBlock, Topic
from apps.learning.models import UserTopicBlockProgress, UserTopicProgress

#: The percentage is reported as a whole number, rounded half up.
_PERCENT_QUANTUM = Decimal("1")


def published_blocks(topic: Topic) -> QuerySet[ContentBlock]:
    """The topic's published blocks.

    Mirrors ``content.selectors.topic_content_blocks(topic, preview_only=False)``
    without materializing the blocks; only the count is needed here.
    """

    return ContentBlock.objects.filter(
        topic=topic,
        status=ContentBlock.Status.PUBLISHED,
    )


def completed_blocks(user, topic: Topic) -> int:
    """Completed rows of ``user`` whose block is a published block of ``topic``."""

    return UserTopicBlockProgress.objects.filter(
        user=user,
        is_complete=True,
        block__topic=topic,
        block__status=ContentBlock.Status.PUBLISHED,
    ).count()


def theory_percent(completed: int, total: int) -> int:
    """``ROUND_HALF_UP(100 × completed / total)``; ``0`` when ``total`` is 0."""

    if total == 0:
        return 0
    ratio = Decimal(100 * completed) / Decimal(total)
    return int(ratio.quantize(_PERCENT_QUANTUM, rounding=ROUND_HALF_UP))


def build_topic_progress_snapshot(user, topic: Topic) -> dict:
    """Build the derived progress payload; never writes.

    A never-touched topic reports ``not_started`` with null timestamps.
    """

    progress = UserTopicProgress.objects.filter(user=user, topic=topic).first()
    total = published_blocks(topic).count()
    completed = completed_blocks(user, topic)
    return {
        "topic": topic.pk,
        "status": progress.status if progress else UserTopicProgress.Status.NOT_STARTED,
        "theory_percent": theory_percent(completed, total),
        "completed_blocks": completed,
        "total_blocks": total,
        "last_opened_at": progress.last_opened_at if progress else None,
        "started_at": progress.started_at if progress else None,
        "completed_at": progress.completed_at if progress else None,
    }
