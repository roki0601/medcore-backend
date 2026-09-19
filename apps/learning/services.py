"""Shared progress-row primitives for the learning write paths (feature 003).

The per-sub-domain services (progress, flashcards, quizzes) all create or move
the ``UserTopicProgress`` row through these helpers, so business rule 5 (the
first theory-block, card or quiz action moves the topic to ``learning``) and the
"``learned`` never regresses" rule have a single implementation.

Every status transition is a conditional SQL update: the row is read once, only
for the ``(user, topic)`` create race, and never as the base of a
read-modify-write. Two concurrent writers therefore cannot lose an update, and an
opening or a first-action write can never overwrite a ``learned`` row.
"""

from __future__ import annotations

from django.db import IntegrityError, models, transaction
from django.db.models import F, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.content.models import Topic
from apps.learning.models import UserTopicProgress

_RETRY_ATTEMPTS = 2

#: The statuses a write path may still move. ``learned`` is terminal, so it is
#: never part of the predicate that writes a status.
NOT_LEARNED_STATUSES = (
    UserTopicProgress.Status.NOT_STARTED,
    UserTopicProgress.Status.LEARNING,
)

#: The rows that still need the ``learning`` transition: a ``not_started`` row,
#: or a ``learning`` row whose ``started_at`` is not stamped yet. An already
#: started ``learning`` row and every ``learned`` row are left untouched.
_NEEDS_LEARNING = models.Q(status=UserTopicProgress.Status.NOT_STARTED) | models.Q(
    status=UserTopicProgress.Status.LEARNING,
    started_at__isnull=True,
)


def _is_unique_race(exc: IntegrityError) -> bool:
    """Whether the error chain is the ``(user, topic)`` uniqueness race."""

    diagnostic = getattr(getattr(exc, "__cause__", None), "diag", None)
    constraint_name = getattr(diagnostic, "constraint_name", None)
    return constraint_name == "learning_usertopicprogress_unique_user_topic"


def _get_or_create(user, topic: Topic) -> UserTopicProgress:
    """Return the progress row, creating it atomically on the unique race.

    Each attempt runs in its own savepoint, so a lost ``(user, topic)`` race
    retries the read instead of failing the surrounding transaction.
    """

    for attempt in range(_RETRY_ATTEMPTS):
        try:
            with transaction.atomic():
                progress, _created = UserTopicProgress.objects.get_or_create(
                    user=user,
                    topic=topic,
                )
            return progress
        except IntegrityError as exc:
            if attempt == 0 and _is_unique_race(exc):
                continue
            raise
    raise RuntimeError("UserTopicProgress creation retry exhausted")


def _move_to_learning(progress: UserTopicProgress, now) -> UserTopicProgress:
    """Apply the conditional ``learning`` transition and reload a changed row.

    ``learned`` is terminal, so the predicate can never match it; ``started_at``
    is stamped exactly once through ``Coalesce``; and an already started
    ``learning`` row is not written again, so the transition stays idempotent.
    """

    updated = (
        UserTopicProgress.objects.filter(
            pk=progress.pk,
            status__in=NOT_LEARNED_STATUSES,
        )
        .filter(_NEEDS_LEARNING)
        .update(
            status=UserTopicProgress.Status.LEARNING,
            started_at=Coalesce(F("started_at"), Value(now)),
            updated_at=now,
        )
    )
    if updated:
        progress.refresh_from_db()
    return progress


def ensure_topic_progress(
    user,
    topic: Topic,
    *,
    opened: bool = False,
) -> UserTopicProgress:
    """Return the user's progress row for ``topic``, creating it when missing.

    ``opened=True`` records the opening of the topic: ``last_opened_at`` becomes
    now and a row that is not yet ``learned`` becomes ``learning`` with
    ``started_at`` filled. ``opened=False`` only guarantees the row exists and
    leaves the status untouched, so the caller can apply an explicit transition
    (for example ``learned``) on top of it. ``learned`` never regresses.
    """

    progress = _get_or_create(user, topic)
    if not opened:
        return progress
    now = timezone.now()
    with transaction.atomic():
        UserTopicProgress.objects.filter(pk=progress.pk).update(
            last_opened_at=now,
            updated_at=now,
        )
        _move_to_learning(progress, now)
    return progress


def touch_topic_learning(user, topic: Topic) -> UserTopicProgress:
    """Move the topic to ``learning`` after a first block/card/attempt action.

    Creates the row when it is missing, fills ``started_at`` once and never
    regresses an already ``learned`` topic.
    """

    progress = _get_or_create(user, topic)
    return _move_to_learning(progress, timezone.now())
