"""Quiz attempt grading (feature 003).

Per question the score is ``max(0, (correct_selected - incorrect_selected) /
correct_answer_count)``; an unanswered question scores ``0``. The quiz score is
the arithmetic mean of the per-question fractions over the attempt's frozen
question set, expressed as a percentage and rounded exactly once with
``ROUND_HALF_UP`` semantics. All arithmetic uses :class:`fractions.Fraction`, so
no floating-point drift can appear.

No pass/fail value is computed: the owner decision on a global pass threshold is
still open, so ``grade_attempt`` returns the score and the per-question breakdown
only.
"""

from __future__ import annotations

from collections.abc import Iterable
from fractions import Fraction
from typing import Any

from apps.content.models import QuizAnswer, QuizQuestion

QuestionResult = dict[str, Any]


def _round_half_up(value: Fraction) -> int:
    """Round a non-negative fraction to the nearest integer, halves upward.

    Exact rational arithmetic reproduces ``decimal.ROUND_HALF_UP`` without a
    ``Decimal`` context (the graded values are never negative).
    """

    floor = value.numerator // value.denominator
    remainder = value - floor
    if remainder * 2 >= 1:
        return floor + 1
    return floor


def _question_score(
    question: QuizQuestion,
    selected_answer_ids: set[int],
) -> tuple[Fraction, list[int], list[int]]:
    """Return the per-question fraction plus the selected and correct answer IDs."""

    answers: list[QuizAnswer] = list(question.answers.all())
    answer_ids = {answer.id for answer in answers}
    correct_ids = sorted(answer.id for answer in answers if answer.is_correct)
    selected_ids = sorted(answer_ids & selected_answer_ids)
    if not correct_ids:
        # Defensive: the content API enforces at least one correct answer.
        return Fraction(0), selected_ids, correct_ids
    correct_selected = sum(1 for answer_id in selected_ids if answer_id in correct_ids)
    incorrect_selected = len(selected_ids) - correct_selected
    numerator = max(correct_selected - incorrect_selected, 0)
    return Fraction(numerator, len(correct_ids)), selected_ids, correct_ids


def grade_attempt(
    questions: Iterable[QuizQuestion],
    selected_answer_ids: Iterable[int],
) -> tuple[int, list[QuestionResult]]:
    """Grade one attempt and return ``(score_percent, results)``.

    ``questions`` is the attempt's frozen question set (``question_ids``); IDs
    outside it are ignored. ``score_percent`` is authoritative and computed from
    the exact fractions; each ``results[].score_percent`` is the per-question
    fraction rounded with ``ROUND_HALF_UP`` for display, so the entries must never
    be averaged to reconstruct the total. ``results`` carries IDs and numeric
    scores only, never question or answer text.
    """

    selected = {int(answer_id) for answer_id in selected_answer_ids}
    fractions: list[Fraction] = []
    results: list[QuestionResult] = []
    for question in questions:
        fraction, selected_ids, correct_ids = _question_score(question, selected)
        fractions.append(fraction)
        results.append(
            {
                "question_id": question.id,
                "selected_answer_ids": selected_ids,
                "correct_answer_ids": correct_ids,
                "score_percent": _round_half_up(fraction * 100),
            }
        )
    if not fractions:
        return 0, results
    mean = sum(fractions, Fraction(0)) / len(fractions)
    return _round_half_up(mean * 100), results
