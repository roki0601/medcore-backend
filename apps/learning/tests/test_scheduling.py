from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from apps.learning.scheduling import (
    ReviewState,
    advance,
    index_of,
    intervals,
    next_review_at,
    reset,
)

NOW = datetime(2026, 9, 19, 10, 0, tzinfo=UTC)


def test_first_know_lands_on_the_first_interval():
    assert advance(ReviewState()) == ReviewState(interval_days=1, repetitions=1)


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (ReviewState(interval_days=1, repetitions=0), ReviewState(3, 1)),
        (ReviewState(interval_days=3, repetitions=4), ReviewState(7, 5)),
        (ReviewState(interval_days=14, repetitions=2), ReviewState(30, 3)),
    ],
)
def test_know_advances_exactly_one_interval(state, expected):
    assert advance(state) == expected


@pytest.mark.parametrize(
    "state",
    [
        ReviewState(interval_days=30, repetitions=0),
        ReviewState(interval_days=30, repetitions=9),
    ],
)
def test_know_is_sticky_on_the_last_interval_but_keeps_counting(state):
    expected = ReviewState(
        interval_days=30,
        repetitions=state.repetitions + 1,
    )
    assert advance(state) == expected


def test_off_ladder_interval_restarts_at_the_first_step():
    assert index_of(0) == -1
    assert index_of(5) == -1
    assert index_of(7) == 2

    assert advance(ReviewState(interval_days=5, repetitions=3)) == ReviewState(1, 4)


def test_repeat_returns_to_the_first_interval_with_a_cleared_counter():
    assert reset() == ReviewState(interval_days=1, repetitions=0)
    assert reset() == ReviewState(intervals()[0], 0)


def test_schedule_follows_the_settings_override(settings):
    settings.LEARNING_FLASHCARD_INTERVALS = (2, 4, 8)

    assert intervals() == (2, 4, 8)
    assert advance(ReviewState()) == ReviewState(2, 1)
    assert advance(ReviewState(interval_days=8, repetitions=1)) == ReviewState(8, 2)
    assert reset() == ReviewState(2, 0)


@pytest.mark.parametrize("interval_days", [1, 3, 7, 14, 30])
def test_next_review_at_adds_the_interval_to_now(interval_days):
    assert next_review_at(NOW, interval_days) == NOW + timedelta(days=interval_days)
