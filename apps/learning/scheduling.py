"""Flashcard review schedule (feature 003).

The ladder is the settings value ``LEARNING_FLASHCARD_INTERVALS`` (days).
``know`` advances exactly one interval and stays on the last one; ``repeat``
resets to the first interval. There is no review history: the caller persists the
returned :class:`ReviewState` on the current ``FlashcardReview`` row.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def intervals() -> tuple[int, ...]:
    """Return the configured interval ladder in ascending day order."""

    ladder = tuple(settings.LEARNING_FLASHCARD_INTERVALS)
    if not ladder:
        raise ImproperlyConfigured("LEARNING_FLASHCARD_INTERVALS must not be empty.")
    return ladder


def index_of(interval_days: int) -> int:
    """Index of ``interval_days`` in the ladder, or ``-1`` when it is absent."""

    ladder = intervals()
    return ladder.index(interval_days) if interval_days in ladder else -1


@dataclass(frozen=True)
class ReviewState:
    """The persisted scheduler state of one user/flashcard pair."""

    interval_days: int = 0
    repetitions: int = 0


def advance(state: ReviewState) -> ReviewState:
    """Apply ``know``: move one interval up and count the repetition.

    A first ``know`` (``interval_days=0``, so ``index_of`` is ``-1``) lands on
    the first interval; a ``know`` on the last interval stays there.
    """

    ladder = intervals()
    index = min(index_of(state.interval_days) + 1, len(ladder) - 1)
    return ReviewState(interval_days=ladder[index], repetitions=state.repetitions + 1)


def reset() -> ReviewState:
    """Apply ``repeat``: back to the first interval with a cleared counter."""

    return ReviewState(interval_days=intervals()[0], repetitions=0)


def next_review_at(now: datetime, interval_days: int) -> datetime:
    """The next due timestamp for a review performed at ``now``."""

    return now + timedelta(days=interval_days)
