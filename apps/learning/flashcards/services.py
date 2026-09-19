"""Flashcard review write path (feature 003).

``know`` and ``repeat`` update the single current ``FlashcardReview`` row of the
user/card pair through :mod:`apps.learning.scheduling`; the Topic progress row is
moved to ``learning`` inside the same transaction (business rule 5). A concurrent
action on the same pair serializes on the row lock taken by ``_find_review``, and
the unique ``(user, flashcard)`` constraint is the backstop for the create race,
so a lost create retries the read instead of failing the transaction.
"""

from __future__ import annotations

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.common.exceptions import APIError
from apps.content.models import Flashcard
from apps.learning.models import FlashcardReview
from apps.learning.scheduling import ReviewState, advance, next_review_at, reset
from apps.learning.services import touch_topic_learning

ACTION_KNOW = "know"
ACTION_REPEAT = "repeat"
REVIEW_ACTIONS = (ACTION_KNOW, ACTION_REPEAT)

_UNIQUE_CONSTRAINT = "learning_flashcardreview_unique_user_flashcard"
_RETRY_ATTEMPTS = 2


def _is_unique_race(exc: IntegrityError) -> bool:
    """Whether the error chain is the ``(user, flashcard)`` uniqueness race."""

    diagnostic = getattr(getattr(exc, "__cause__", None), "diag", None)
    return getattr(diagnostic, "constraint_name", None) == _UNIQUE_CONSTRAINT


def _find_review(user, flashcard: Flashcard) -> FlashcardReview | None:
    """The current review row of the pair, locked for the calling transaction.

    ``select_for_update`` makes two concurrent actions on the same user/card
    serialize: the second transaction reads the row the first one committed and
    advances the schedule again, so no update is lost. It must be called inside
    the ``review_flashcard`` transaction.
    """

    return (
        FlashcardReview.objects.select_for_update()
        .filter(user=user, flashcard=flashcard)
        .first()
    )


def _get_or_create_review(
    user,
    flashcard: Flashcard,
) -> tuple[FlashcardReview, bool]:
    """Return ``(review, created)``, retrying the read on the unique race.

    Each create attempt runs in its own savepoint, so a lost ``(user, flashcard)``
    race rolls back only that statement and the caller's transaction stays usable.
    """

    review = _find_review(user, flashcard)
    if review is not None:
        return review, False
    for _attempt in range(_RETRY_ATTEMPTS):
        try:
            with transaction.atomic():
                return (
                    FlashcardReview.objects.create(user=user, flashcard=flashcard),
                    True,
                )
        except IntegrityError as exc:
            if not _is_unique_race(exc):
                raise
            review = _find_review(user, flashcard)
            if review is not None:
                return review, False
    raise RuntimeError("FlashcardReview creation retry exhausted")


def _apply_action(action: str, review: FlashcardReview, now) -> FlashcardReview:
    state = (
        advance(ReviewState(review.interval_days, review.repetitions))
        if action == ACTION_KNOW
        else reset()
    )
    review.interval_days = state.interval_days
    review.repetitions = state.repetitions
    review.last_reviewed_at = now
    review.next_review_at = next_review_at(now, state.interval_days)
    return review


def review_flashcard(
    user,
    flashcard: Flashcard,
    *,
    action: str,
    now=None,
) -> tuple[FlashcardReview, bool]:
    """Apply ``know``/``repeat`` to the current review row of ``user``/``flashcard``.

    Returns ``(review, created)`` so the transport can answer 201 on the first
    review of the card and 200 afterwards. The Topic progress row is moved to
    ``learning`` in the same transaction and ``learned`` never regresses.
    """

    if action not in REVIEW_ACTIONS:
        raise APIError(
            "Request validation failed.",
            code="VALIDATION_ERROR",
            status_code=422,
            fields={"action": ["Invalid action."]},
        )
    if now is None:
        now = timezone.now()
    with transaction.atomic():
        review, created = _get_or_create_review(user, flashcard)
        _apply_action(action, review, now)
        review.save(
            update_fields=[
                "interval_days",
                "repetitions",
                "last_reviewed_at",
                "next_review_at",
                "updated_at",
            ]
        )
        touch_topic_learning(user, flashcard.topic)
    return review, created
