from __future__ import annotations

import pytest

from apps.learning.scoring import grade_attempt


def _question(make_quiz_question, make_quiz_answer, quiz, *, correct: int, wrong: int):
    question = make_quiz_question(quiz)
    correct_answers = [
        make_quiz_answer(question, text=f"Correct {index}", is_correct=True)
        for index in range(correct)
    ]
    wrong_answers = [
        make_quiz_answer(question, text=f"Wrong {index}") for index in range(wrong)
    ]
    return question, correct_answers, wrong_answers


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("selection", "expected"),
    [("correct", 100), ("wrong", 0), ("none", 0)],
)
def test_single_correct_answer_question_scores_full_credit_only_when_selected(
    selection,
    expected,
    make_topic,
    make_quiz,
    make_quiz_question,
    make_quiz_answer,
):
    quiz = make_quiz(make_topic())
    question, correct, wrong = _question(
        make_quiz_question, make_quiz_answer, quiz, correct=1, wrong=1
    )
    selected = {
        "correct": [correct[0].id],
        "wrong": [wrong[0].id],
        "none": [],
    }[selection]

    score, results = grade_attempt([question], selected)

    assert score == expected
    assert results[0]["score_percent"] == expected


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("selected_correct", "selected_wrong", "expected"),
    [
        (1, 0, 50),
        (2, 0, 100),
        (2, 1, 50),
        (0, 1, 0),
        (2, 3, 0),
    ],
)
def test_multiple_correct_answers_earn_partial_credit_with_a_zero_floor(
    selected_correct,
    selected_wrong,
    expected,
    make_topic,
    make_quiz,
    make_quiz_question,
    make_quiz_answer,
):
    quiz = make_quiz(make_topic())
    question, correct, wrong = _question(
        make_quiz_question, make_quiz_answer, quiz, correct=2, wrong=3
    )
    selected = [answer.id for answer in correct[:selected_correct]]
    selected += [answer.id for answer in wrong[:selected_wrong]]

    score, _results = grade_attempt([question], selected)

    assert score == expected


@pytest.mark.django_db
def test_quiz_score_is_the_mean_over_the_frozen_question_set(
    make_topic,
    make_quiz,
    make_quiz_question,
    make_quiz_answer,
):
    quiz = make_quiz(make_topic())
    solved, solved_correct, _ = _question(
        make_quiz_question, make_quiz_answer, quiz, correct=1, wrong=0
    )
    unanswered, _, _ = _question(
        make_quiz_question, make_quiz_answer, quiz, correct=1, wrong=1
    )

    score, results = grade_attempt([solved, unanswered], [solved_correct[0].id])

    assert score == 50
    assert [entry["score_percent"] for entry in results] == [100, 0]


@pytest.mark.django_db
def test_empty_frozen_question_set_scores_zero(make_topic, make_quiz):
    score, results = grade_attempt([], [1, 2, 3])

    assert (score, results) == (0, [])


@pytest.mark.django_db
def test_score_rounds_half_up_at_the_boundary(
    make_topic,
    make_quiz,
    make_quiz_question,
    make_quiz_answer,
):
    """One of eight correct answers is 12.5%, which rounds up to 13%."""

    quiz = make_quiz(make_topic())
    question, correct, _ = _question(
        make_quiz_question, make_quiz_answer, quiz, correct=8, wrong=0
    )

    score, results = grade_attempt([question], [correct[0].id])

    assert score == 13
    assert results[0]["score_percent"] == 13


@pytest.mark.django_db
def test_rounded_question_scores_cannot_reconstruct_the_stored_total(
    make_topic,
    make_quiz,
    make_quiz_question,
    make_quiz_answer,
):
    """The stored total is authoritative; the display entries are display-rounded."""

    quiz = make_quiz(make_topic())
    hard, hard_correct, _ = _question(
        make_quiz_question, make_quiz_answer, quiz, correct=8, wrong=0
    )
    unanswered, _, _ = _question(
        make_quiz_question, make_quiz_answer, quiz, correct=1, wrong=1
    )

    score, results = grade_attempt([hard, unanswered], [hard_correct[0].id])

    # Exact mean: (1/8 + 0) / 2 = 6.25% -> 6. Averaging the displayed 13% and 0%
    # would give 7%.
    assert score == 6
    assert [entry["score_percent"] for entry in results] == [13, 0]


@pytest.mark.django_db
def test_question_without_a_correct_answer_scores_zero(
    make_topic,
    make_quiz,
    make_quiz_question,
    make_quiz_answer,
):
    """Defensive: grading must not divide by zero on a question without a
    correct answer, which the content API forbids."""

    quiz = make_quiz(make_topic())
    question, _, wrong = _question(
        make_quiz_question, make_quiz_answer, quiz, correct=0, wrong=2
    )

    score, results = grade_attempt([question], [wrong[0].id])

    assert score == 0
    assert results[0]["correct_answer_ids"] == []


@pytest.mark.django_db
def test_results_carry_ids_and_numeric_scores_only(
    make_topic,
    make_quiz,
    make_quiz_question,
    make_quiz_answer,
):
    quiz = make_quiz(make_topic())
    question, correct, wrong = _question(
        make_quiz_question, make_quiz_answer, quiz, correct=1, wrong=1
    )
    _, foreign_correct, _ = _question(
        make_quiz_question, make_quiz_answer, quiz, correct=1, wrong=0
    )

    score, results = grade_attempt(
        [question],
        [foreign_correct[0].id, wrong[0].id, correct[0].id],
    )

    assert score == 0
    assert set(results[0]) == {
        "question_id",
        "selected_answer_ids",
        "correct_answer_ids",
        "score_percent",
    }
    assert results[0]["question_id"] == question.id
    # An answer of another question is not part of this question's selection.
    assert results[0]["selected_answer_ids"] == sorted([correct[0].id, wrong[0].id])
    assert results[0]["correct_answer_ids"] == [correct[0].id]
    assert foreign_correct[0].id not in results[0]["selected_answer_ids"]
