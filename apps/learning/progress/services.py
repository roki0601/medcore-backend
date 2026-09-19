"""Write use cases for topic progress and theory-block completion (feature 003).

The shared progress-row primitives live in ``apps.learning.services``; these
services own the progress sub-domain's transitions on top of them. The manual
``learned`` transition never regresses and is the only path to ``learned``
(score-based auto-completion is deferred, see the decision record).
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.common.exceptions import APIError
from apps.content.models import ContentBlock, Topic
from apps.learning.models import UserTopicBlockProgress, UserTopicProgress
from apps.learning.services import (
    NOT_LEARNED_STATUSES,
    ensure_topic_progress,
    touch_topic_learning,
)


def open_topic(user, topic: Topic) -> UserTopicProgress:
    """Record an opening: ``last_opened_at = now``; move a new row to ``learning``."""

    return ensure_topic_progress(user, topic, opened=True)


def mark_topic_learned(user, topic: Topic) -> UserTopicProgress:
    """Apply the explicit manual ``learned`` transition; never regress.

    The row is created and moved to ``learned`` inside one transaction, so it is
    never committed as ``not_started`` first. The conditional update matches only
    a row that is not learned yet, so a concurrent ``{"opened": true}`` can never
    roll the status back, and ``completed_at`` is stamped on the first transition
    only.
    """

    now = timezone.now()
    with transaction.atomic():
        progress = ensure_topic_progress(user, topic)
        updated = UserTopicProgress.objects.filter(
            pk=progress.pk,
            status__in=NOT_LEARNED_STATUSES,
        ).update(
            status=UserTopicProgress.Status.LEARNED,
            completed_at=now,
            updated_at=now,
        )
        if updated:
            progress.refresh_from_db()
    return progress


def complete_topic_block(
    user,
    topic: Topic,
    block_id: int,
) -> tuple[UserTopicProgress, bool]:
    """Mark a published block of ``topic`` complete; return ``(progress, created)``.

    The topic is derived from the block: a block of another topic (or an
    unpublished/missing block) is a 404. The write is an idempotent upsert, so a
    repeat returns the same row with ``created=False``.
    """

    block = _resolve_published_block(topic, block_id)
    now = timezone.now()
    with transaction.atomic():
        progress = touch_topic_learning(user, topic)
        row, created = UserTopicBlockProgress.objects.get_or_create(
            user=user,
            block=block,
            defaults={"is_complete": True, "completed_at": now},
        )
        if not created and not row.is_complete:
            row.is_complete = True
            row.completed_at = now
            row.save(update_fields=["is_complete", "completed_at", "updated_at"])
    return progress, created


def _resolve_published_block(topic: Topic, block_id: int) -> ContentBlock:
    """Resolve a published block of ``topic`` or raise 404 ``RESOURCE_NOT_FOUND``."""

    block = ContentBlock.objects.filter(
        pk=block_id,
        topic=topic,
        status=ContentBlock.Status.PUBLISHED,
    ).first()
    if block is None:
        raise APIError(
            "Resource not found.", code="RESOURCE_NOT_FOUND", status_code=404
        )
    return block
