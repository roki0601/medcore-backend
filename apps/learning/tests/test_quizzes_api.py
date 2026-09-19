"""Quiz and quiz-attempt API behaviour (feature 003, tasks T010/T011).

The file covers the attempt lifecycle (start/resume/submit/retake), the
validation and error contract, the grading policy through the transport, the
absence of any correctness leak before submit, the access/ownership boundary,
throttling and the two real concurrency conflicts.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.db import connections
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken

from apps.content.models import (
    Quiz,
    QuizAnswer,
    QuizQuestion,
    Section,
    Subject,
    Topic,
)
from apps.learning.models import QuizAttempt, UserTopicProgress
from apps.learning.quizzes import services
from apps.learning.quizzes.serializers import MAX_SELECTED_ANSWER_IDS

User = get_user_model()

QUIZ_LIST_URL = "/api/v1/topics/{topic_id}/quizzes/"
QUIZ_DETAIL_URL = "/api/v1/quizzes/{pk}/"
ATTEMPT_START_URL = "/api/v1/quizzes/{pk}/attempts/"
ATTEMPT_DETAIL_URL = "/api/v1/quiz-attempts/{pk}/"
ATTEMPT_SUBMIT_URL = "/api/v1/quiz-attempts/{pk}/submit/"


def _add_question(
    make_quiz_question,
    make_quiz_answer,
    quiz,
    *,
    correct: int,
    wrong: int,
    position: int | None = None,
):
    """One question of ``quiz`` with ``correct`` correct and ``wrong`` answers."""

    question = make_quiz_question(quiz, position=position)
    correct_answers = [
        make_quiz_answer(question, text=f"Correct {index}", is_correct=True)
        for index in range(correct)
    ]
    wrong_answers = [
        make_quiz_answer(question, text=f"Wrong {index}") for index in range(wrong)
    ]
    return question, correct_answers, wrong_answers


def _start(api_client, quiz) -> dict:
    response = api_client.post(ATTEMPT_START_URL.format(pk=quiz.pk), {}, format="json")
    assert response.status_code == 201
    return response.json()


def _submit(api_client, attempt_id: int):
    return api_client.post(ATTEMPT_SUBMIT_URL.format(pk=attempt_id), {}, format="json")


def _save(api_client, attempt_id: int, answer_ids: list[int]):
    return api_client.patch(
        ATTEMPT_DETAIL_URL.format(pk=attempt_id),
        {"selected_answer_ids": answer_ids},
        format="json",
    )


# ---------------------------------------------------------------------------
# Quiz reads.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_topic_quiz_list_derives_question_count_and_best_score(
    api_client,
    authenticate,
    make_user,
    make_topic,
    make_quiz,
    make_quiz_question,
    make_quiz_answer,
):
    """Ordering, the derived question count and the per-user maximum score."""

    user = make_user()
    authenticate(api_client, user)
    topic = make_topic()
    second = make_quiz(topic, title="Second", position=2)
    first = make_quiz(topic, title="First", position=1)
    _add_question(make_quiz_question, make_quiz_answer, first, correct=1, wrong=1)
    _add_question(make_quiz_question, make_quiz_answer, first, correct=2, wrong=0)
    _add_question(make_quiz_question, make_quiz_answer, second, correct=1, wrong=1)
    for score in (40, 80):
        QuizAttempt.objects.create(
            user=user,
            quiz=first,
            status=QuizAttempt.Status.SUBMITTED,
            score_percent=score,
            submitted_at=timezone.now(),
        )
    QuizAttempt.objects.create(
        user=make_user(username="other"),
        quiz=first,
        status=QuizAttempt.Status.SUBMITTED,
        score_percent=100,
        submitted_at=timezone.now(),
    )

    response = api_client.get(QUIZ_LIST_URL.format(topic_id=topic.pk))

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
    assert body["results"][0] == {
        "id": first.pk,
        "topic": topic.pk,
        "title": "First",
        "description": "",
        "position": 1,
        "question_count": 2,
        "best_score_percent": 80,
    }
    assert body["results"][1]["question_count"] == 1
    assert body["results"][1]["best_score_percent"] is None
    assert "is_correct" not in response.content.decode()


@pytest.mark.django_db
def test_quiz_detail_exposes_ordered_questions_without_correctness(
    api_client,
    authenticate,
    make_user,
    make_topic,
    make_quiz,
    make_quiz_question,
    make_quiz_answer,
):
    """``(position, id)`` ordering for questions and answers, never correctness."""

    authenticate(api_client, make_user())
    quiz = make_quiz(make_topic())
    late = make_quiz_question(quiz, text="Second", position=2)
    early = make_quiz_question(quiz, text="First", position=1)
    make_quiz_answer(late, text="Late answer", is_correct=True)
    early_wrong = make_quiz_answer(early, text="Early wrong", position=2)
    early_correct = make_quiz_answer(early, text="Early correct", position=1)

    response = api_client.get(QUIZ_DETAIL_URL.format(pk=quiz.pk))

    assert response.status_code == 200
    body = response.json()
    assert body["question_count"] == 2
    assert body["best_score_percent"] is None
    assert [question["id"] for question in body["questions"]] == [early.pk, late.pk]
    assert [answer["id"] for answer in body["questions"][0]["answers"]] == [
        early_correct.pk,
        early_wrong.pk,
    ]
    assert set(body["questions"][0]["answers"][0]) == {"id", "text", "position"}
    assert "is_correct" not in response.content.decode()


# ---------------------------------------------------------------------------
# Attempt lifecycle.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_start_creates_one_active_attempt_then_returns_it(
    api_client,
    authenticate,
    make_user,
    make_topic,
    make_quiz,
    make_quiz_question,
    make_quiz_answer,
):
    """201 with a frozen empty attempt, then 200 with the same row, and progress."""

    user = make_user()
    authenticate(api_client, user)
    topic = make_topic()
    quiz = make_quiz(topic)
    later = make_quiz_question(quiz, text="Later", position=2)
    first = make_quiz_question(quiz, text="First", position=1)
    for question in (first, later):
        make_quiz_answer(question, is_correct=True)
        make_quiz_answer(question)

    created = api_client.post(
        ATTEMPT_START_URL.format(pk=quiz.pk),
        {},
        format="json",
    )

    assert created.status_code == 201
    body = created.json()
    assert body["quiz"] == quiz.pk
    assert body["topic"] == topic.pk
    assert body["status"] == "active"
    assert body["question_ids"] == [first.pk, later.pk]
    assert body["selected_answer_ids"] == []
    assert [item["id"] for item in body["questions"]] == [first.pk, later.pk]
    assert body["results"] is None
    assert body["score_percent"] is None
    assert body["submitted_at"] is None
    assert body["started_at"] is not None
    assert "is_correct" not in created.content.decode()

    progress = UserTopicProgress.objects.get(user=user, topic=topic)
    assert progress.status == UserTopicProgress.Status.LEARNING
    assert progress.started_at is not None

    repeated = api_client.post(
        ATTEMPT_START_URL.format(pk=quiz.pk),
        {},
        format="json",
    )

    assert repeated.status_code == 200
    assert repeated.json()["id"] == body["id"]
    assert QuizAttempt.objects.filter(quiz=quiz).count() == 1


@pytest.mark.django_db
def test_patch_replaces_the_whole_selection_and_resumes(
    api_client,
    authenticate,
    make_user,
    make_topic,
    make_quiz,
    make_quiz_question,
    make_quiz_answer,
):
    """Full replacement with collapsed duplicates, persisted for a resume."""

    authenticate(api_client, make_user())
    quiz = make_quiz(make_topic())
    _question, correct, wrong = _add_question(
        make_quiz_question, make_quiz_answer, quiz, correct=1, wrong=2
    )
    attempt = _start(api_client, quiz)

    saved = _save(api_client, attempt["id"], [correct[0].pk])

    assert saved.status_code == 200
    assert saved.json()["selected_answer_ids"] == [correct[0].pk]

    expected = sorted([correct[0].pk, wrong[1].pk])
    replaced = _save(
        api_client,
        attempt["id"],
        [wrong[1].pk, correct[0].pk, correct[0].pk],
    )

    assert replaced.status_code == 200
    assert replaced.json()["selected_answer_ids"] == expected
    stored = QuizAttempt.objects.get(pk=attempt["id"])
    assert stored.answers_state == {"selected_answer_ids": expected}
    resumed = api_client.get(ATTEMPT_DETAIL_URL.format(pk=attempt["id"]))
    assert resumed.json()["selected_answer_ids"] == expected

    cleared = _save(api_client, attempt["id"], [])

    assert cleared.status_code == 200
    assert cleared.json()["selected_answer_ids"] == []


@pytest.mark.django_db
def test_patch_rejects_answers_outside_the_frozen_question_set(
    api_client,
    authenticate,
    make_user,
    make_topic,
    make_quiz,
    make_quiz_question,
    make_quiz_answer,
):
    """A foreign quiz, a question added after start and an unknown id are 422."""

    authenticate(api_client, make_user())
    quiz = make_quiz(make_topic())
    _add_question(make_quiz_question, make_quiz_answer, quiz, correct=1, wrong=1)
    foreign_quiz = make_quiz(make_topic(), title="Other quiz")
    _foreign_question, foreign_correct, _wrong = _add_question(
        make_quiz_question, make_quiz_answer, foreign_quiz, correct=1, wrong=0
    )
    attempt = _start(api_client, quiz)
    _late_question, late_correct, _late_wrong = _add_question(
        make_quiz_question, make_quiz_answer, quiz, correct=1, wrong=1
    )

    cases = {
        "another quiz": foreign_correct[0].pk,
        "question added after start": late_correct[0].pk,
        "unknown id": 999999,
    }
    for label, answer_id in cases.items():
        response = _save(api_client, attempt["id"], [answer_id])
        assert response.status_code == 422, label
        assert response.json()["code"] == "INVALID_ANSWER", label

    resumed = api_client.get(ATTEMPT_DETAIL_URL.format(pk=attempt["id"])).json()
    assert resumed["selected_answer_ids"] == []


@pytest.mark.django_db
def test_submitted_attempt_cannot_be_saved_or_submitted_again(
    api_client,
    authenticate,
    make_user,
    make_topic,
    make_quiz,
    make_quiz_question,
    make_quiz_answer,
):
    """The frozen attempt is immutable: both mutations are 409 and change nothing."""

    authenticate(api_client, make_user())
    quiz = make_quiz(make_topic())
    _question, correct, wrong = _add_question(
        make_quiz_question, make_quiz_answer, quiz, correct=1, wrong=1
    )
    attempt = _start(api_client, quiz)
    assert _save(api_client, attempt["id"], [correct[0].pk]).status_code == 200
    frozen = _submit(api_client, attempt["id"]).json()

    rejected_save = _save(api_client, attempt["id"], [wrong[0].pk])
    rejected_submit = _submit(api_client, attempt["id"])

    for response in (rejected_save, rejected_submit):
        assert response.status_code == 409
        assert response.json()["code"] == "ATTEMPT_ALREADY_SUBMITTED"
    stored = QuizAttempt.objects.get(pk=attempt["id"])
    assert stored.status == QuizAttempt.Status.SUBMITTED
    assert stored.score_percent == frozen["score_percent"]
    assert stored.results == frozen["results"]
    assert stored.answers_state == {"selected_answer_ids": [correct[0].pk]}


# ---------------------------------------------------------------------------
# Grading through the API.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("first_correct", "first_wrong", "second_answered", "expected"),
    [
        (2, 0, True, 100),
        (1, 0, True, 75),
        (2, 1, False, 25),
        (2, 2, True, 50),
        (0, 2, False, 0),
        (0, 0, False, 0),
    ],
)
def test_submit_scores_the_frozen_set_through_the_api(
    first_correct,
    first_wrong,
    second_answered,
    expected,
    api_client,
    authenticate,
    make_user,
    make_topic,
    make_quiz,
    make_quiz_question,
    make_quiz_answer,
):
    """Partial credit, the negative floor, unanswered questions and no pass flag.

    The frozen set is one question with two correct and two wrong answers plus one
    single-answer question; the stored score is their arithmetic mean.
    """

    authenticate(api_client, make_user())
    quiz = make_quiz(make_topic())
    first, correct_answers, wrong_answers = _add_question(
        make_quiz_question, make_quiz_answer, quiz, correct=2, wrong=2
    )
    second, second_correct, _second_wrong = _add_question(
        make_quiz_question, make_quiz_answer, quiz, correct=1, wrong=1
    )
    attempt = _start(api_client, quiz)
    selected = [answer.pk for answer in correct_answers[:first_correct]]
    selected += [answer.pk for answer in wrong_answers[:first_wrong]]
    if second_answered:
        selected.append(second_correct[0].pk)
    assert _save(api_client, attempt["id"], selected).status_code == 200

    response = _submit(api_client, attempt["id"])

    assert response.status_code == 200
    body = response.json()
    assert body["score_percent"] == expected
    assert body["status"] == "submitted"
    assert body["submitted_at"] is not None
    assert [entry["question_id"] for entry in body["results"]] == [first.pk, second.pk]
    assert "passed" not in body
    assert QuizAttempt.objects.get(pk=attempt["id"]).score_percent == expected


@pytest.mark.django_db
def test_submit_rounds_the_stored_score_half_up(
    api_client,
    authenticate,
    make_user,
    make_topic,
    make_quiz,
    make_quiz_question,
    make_quiz_answer,
):
    """One of eight correct answers is 12.5%, which the stored score rounds to 13."""

    authenticate(api_client, make_user())
    quiz = make_quiz(make_topic())
    _question, correct, _wrong = _add_question(
        make_quiz_question, make_quiz_answer, quiz, correct=8, wrong=0
    )
    attempt = _start(api_client, quiz)
    assert _save(api_client, attempt["id"], [correct[0].pk]).status_code == 200

    body = _submit(api_client, attempt["id"]).json()

    assert body["score_percent"] == 13
    assert body["results"][0]["score_percent"] == 13
    assert "passed" not in body


@pytest.mark.django_db
def test_grading_uses_the_current_flags_while_submitted_results_stay_frozen(
    api_client,
    authenticate,
    make_user,
    make_topic,
    make_quiz,
    make_quiz_question,
    make_quiz_answer,
):
    """A correctness flip after start is graded at submit; older results stay."""

    authenticate(api_client, make_user())
    quiz = make_quiz(make_topic())
    _question, correct, wrong = _add_question(
        make_quiz_question, make_quiz_answer, quiz, correct=1, wrong=1
    )
    first_attempt = _start(api_client, quiz)
    assert _save(api_client, first_attempt["id"], [correct[0].pk]).status_code == 200
    assert _submit(api_client, first_attempt["id"]).json()["score_percent"] == 100
    frozen_results = QuizAttempt.objects.get(pk=first_attempt["id"]).results

    QuizAnswer.objects.filter(pk=correct[0].pk).update(is_correct=False)
    QuizAnswer.objects.filter(pk=wrong[0].pk).update(is_correct=True)

    second_attempt = _start(api_client, quiz)
    assert second_attempt["id"] != first_attempt["id"]
    assert _save(api_client, second_attempt["id"], [wrong[0].pk]).status_code == 200

    body = _submit(api_client, second_attempt["id"]).json()

    assert body["score_percent"] == 100
    assert body["results"][0]["correct_answer_ids"] == [wrong[0].pk]
    stored = QuizAttempt.objects.get(pk=first_attempt["id"])
    assert stored.results == frozen_results
    assert stored.results[0]["correct_answer_ids"] == [correct[0].pk]
    assert stored.score_percent == 100


@pytest.mark.django_db
def test_retake_keeps_the_first_attempt_and_derives_the_best_score(
    api_client,
    authenticate,
    make_user,
    make_topic,
    make_quiz,
    make_quiz_question,
    make_quiz_answer,
):
    """A second attempt is retained and the best score is the derived maximum."""

    user = make_user()
    authenticate(api_client, user)
    topic = make_topic()
    quiz = make_quiz(topic)
    _question, correct, wrong = _add_question(
        make_quiz_question, make_quiz_answer, quiz, correct=1, wrong=1
    )
    first_attempt = _start(api_client, quiz)
    assert _save(api_client, first_attempt["id"], [wrong[0].pk]).status_code == 200
    assert _submit(api_client, first_attempt["id"]).json()["score_percent"] == 0

    second_attempt = _start(api_client, quiz)

    assert second_attempt["id"] != first_attempt["id"]
    assert QuizAttempt.objects.filter(user=user, quiz=quiz).count() == 2
    assert _save(api_client, second_attempt["id"], [correct[0].pk]).status_code == 200
    assert _submit(api_client, second_attempt["id"]).json()["score_percent"] == 100

    retained = QuizAttempt.objects.get(pk=first_attempt["id"])
    assert retained.score_percent == 0
    assert retained.answers_state == {"selected_answer_ids": [wrong[0].pk]}
    detail = api_client.get(QUIZ_DETAIL_URL.format(pk=quiz.pk)).json()
    assert detail["best_score_percent"] == 100
    listed = api_client.get(QUIZ_LIST_URL.format(topic_id=topic.pk)).json()
    assert listed["results"][0]["best_score_percent"] == 100


@pytest.mark.django_db
def test_question_added_after_start_stays_out_of_the_in_flight_attempt(
    api_client,
    authenticate,
    make_user,
    make_topic,
    make_quiz,
    make_quiz_question,
    make_quiz_answer,
):
    """The frozen set drives the payload, the accepted answers and the denominator."""

    authenticate(api_client, make_user())
    quiz = make_quiz(make_topic())
    question, correct, _wrong = _add_question(
        make_quiz_question, make_quiz_answer, quiz, correct=1, wrong=1
    )
    attempt = _start(api_client, quiz)
    assert attempt["question_ids"] == [question.pk]
    _late_question, late_correct, _late_wrong = _add_question(
        make_quiz_question, make_quiz_answer, quiz, correct=1, wrong=1
    )

    active = api_client.get(ATTEMPT_DETAIL_URL.format(pk=attempt["id"]))

    assert active.status_code == 200
    payload = active.json()
    assert payload["question_ids"] == [question.pk]
    assert [item["id"] for item in payload["questions"]] == [question.pk]
    assert payload["results"] is None
    assert "is_correct" not in active.content.decode()

    assert _save(api_client, attempt["id"], [correct[0].pk]).status_code == 200
    submitted = _submit(api_client, attempt["id"]).json()

    assert submitted["score_percent"] == 100
    assert [entry["question_id"] for entry in submitted["results"]] == [question.pk]
    detail = api_client.get(QUIZ_DETAIL_URL.format(pk=quiz.pk)).json()
    assert detail["question_count"] == 2
    assert late_correct[0].pk not in submitted["results"][0]["correct_answer_ids"]


# ---------------------------------------------------------------------------
# Access, ownership and the validation contract.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_another_users_attempt_is_not_found(
    api_client,
    authenticate,
    make_user,
    make_topic,
    make_quiz,
    make_quiz_question,
    make_quiz_answer,
):
    """Reading, saving and submitting a foreign attempt are all 404."""

    owner = make_user(username="owner")
    authenticate(api_client, owner)
    quiz = make_quiz(make_topic())
    _question, correct, _wrong = _add_question(
        make_quiz_question, make_quiz_answer, quiz, correct=1, wrong=1
    )
    attempt = _start(api_client, quiz)

    authenticate(api_client, make_user(username="intruder"))
    responses = (
        api_client.get(ATTEMPT_DETAIL_URL.format(pk=attempt["id"])),
        _save(api_client, attempt["id"], [correct[0].pk]),
        _submit(api_client, attempt["id"]),
    )

    for response in responses:
        assert response.status_code == 404
        assert response.json()["code"] == "RESOURCE_NOT_FOUND"
    assert QuizAttempt.objects.get(pk=attempt["id"]).status == QuizAttempt.Status.ACTIVE


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("method", "target", "payload"),
    [
        ("get", "list", None),
        ("get", "detail", None),
        ("post", "start", {}),
        ("get", "attempt", None),
        ("patch", "attempt", {"selected_answer_ids": []}),
        ("post", "submit", {}),
    ],
)
def test_anonymous_requests_are_rejected(
    method,
    target,
    payload,
    api_client,
    make_user,
    make_topic,
    make_quiz,
    make_quiz_question,
    make_quiz_answer,
):
    """Every quiz route requires authentication and never touches learning state."""

    quiz = make_quiz(make_topic())
    question, _correct, _wrong = _add_question(
        make_quiz_question, make_quiz_answer, quiz, correct=1, wrong=1
    )
    attempt = QuizAttempt.objects.create(
        user=make_user(),
        quiz=quiz,
        question_ids=[question.pk],
        answers_state={"selected_answer_ids": []},
    )
    urls = {
        "list": QUIZ_LIST_URL.format(topic_id=quiz.topic_id),
        "detail": QUIZ_DETAIL_URL.format(pk=quiz.pk),
        "start": ATTEMPT_START_URL.format(pk=quiz.pk),
        "attempt": ATTEMPT_DETAIL_URL.format(pk=attempt.pk),
        "submit": ATTEMPT_SUBMIT_URL.format(pk=attempt.pk),
    }
    request = getattr(api_client, method)

    response = request(urls[target], payload, format="json")

    assert response.status_code == 401
    assert response.json()["code"] == "AUTHENTICATION_REQUIRED"
    assert QuizAttempt.objects.count() == 1
    stored = QuizAttempt.objects.get(pk=attempt.pk)
    assert stored.status == QuizAttempt.Status.ACTIVE
    assert stored.answers_state == {"selected_answer_ids": []}


@pytest.mark.django_db
def test_quiz_routes_recheck_topic_access(
    api_client,
    authenticate,
    make_user,
    make_quiz,
    make_quiz_question,
    make_quiz_answer,
    paid_topic,
    draft_topic,
):
    """A paid denial is 403 and an unpublished topic is 404, never state."""

    authenticate(api_client, make_user())
    paid_quiz = make_quiz(paid_topic)
    draft_quiz = make_quiz(draft_topic)
    for quiz in (paid_quiz, draft_quiz):
        _add_question(make_quiz_question, make_quiz_answer, quiz, correct=1, wrong=1)

    denied = (
        api_client.get(QUIZ_LIST_URL.format(topic_id=paid_topic.pk)),
        api_client.get(QUIZ_DETAIL_URL.format(pk=paid_quiz.pk)),
        api_client.post(ATTEMPT_START_URL.format(pk=paid_quiz.pk), {}, format="json"),
    )

    for response in denied:
        assert response.status_code == 403
        assert response.json()["code"] == "TOPIC_ENTITLEMENT_REQUIRED"
    assert QuizAttempt.objects.count() == 0

    unpublished = (
        api_client.get(QUIZ_LIST_URL.format(topic_id=draft_topic.pk)),
        api_client.get(QUIZ_DETAIL_URL.format(pk=draft_quiz.pk)),
    )

    for response in unpublished:
        assert response.status_code == 404
        assert response.json()["code"] == "RESOURCE_NOT_FOUND"


@pytest.mark.django_db
def test_patch_rejects_unknown_fields_and_malformed_bodies(
    api_client,
    authenticate,
    make_user,
    make_topic,
    make_quiz,
    make_quiz_question,
    make_quiz_answer,
):
    """Unknown field, missing field and a non-integer id are all 422."""

    authenticate(api_client, make_user())
    quiz = make_quiz(make_topic())
    _question, correct, _wrong = _add_question(
        make_quiz_question, make_quiz_answer, quiz, correct=1, wrong=1
    )
    attempt = _start(api_client, quiz)

    unknown = api_client.patch(
        ATTEMPT_DETAIL_URL.format(pk=attempt["id"]),
        {"selected_answer_ids": [correct[0].pk], "unexpected": 1},
        format="json",
    )
    empty = api_client.patch(
        ATTEMPT_DETAIL_URL.format(pk=attempt["id"]),
        {},
        format="json",
    )
    malformed = _save(api_client, attempt["id"], ["not-an-id"])

    assert unknown.status_code == 422
    assert unknown.json()["code"] == "VALIDATION_ERROR"
    assert unknown.json()["fields"] == {"unexpected": ["Unknown field."]}
    assert empty.status_code == 422
    assert empty.json()["code"] == "VALIDATION_ERROR"
    assert "selected_answer_ids" in empty.json()["fields"]
    assert malformed.status_code == 422
    assert malformed.json()["code"] == "VALIDATION_ERROR"
    stored = api_client.get(ATTEMPT_DETAIL_URL.format(pk=attempt["id"])).json()
    assert stored["selected_answer_ids"] == []


@pytest.mark.django_db
def test_patch_rejects_an_oversized_selection(
    api_client,
    authenticate,
    make_user,
    make_topic,
    make_quiz,
    make_quiz_question,
    make_quiz_answer,
):
    """A selection beyond the transport bound is 422; the bound itself is accepted."""

    authenticate(api_client, make_user())
    quiz = make_quiz(make_topic())
    _question, correct, _wrong = _add_question(
        make_quiz_question, make_quiz_answer, quiz, correct=1, wrong=1
    )
    attempt = _start(api_client, quiz)

    oversized = _save(
        api_client,
        attempt["id"],
        [correct[0].pk] * (MAX_SELECTED_ANSWER_IDS + 1),
    )

    assert oversized.status_code == 422
    assert oversized.json()["code"] == "VALIDATION_ERROR"
    assert "selected_answer_ids" in oversized.json()["fields"]
    stored = api_client.get(ATTEMPT_DETAIL_URL.format(pk=attempt["id"])).json()
    assert stored["selected_answer_ids"] == []

    boundary = _save(
        api_client,
        attempt["id"],
        [correct[0].pk] * MAX_SELECTED_ANSWER_IDS,
    )

    assert boundary.status_code == 200
    assert boundary.json()["selected_answer_ids"] == [correct[0].pk]


@pytest.mark.django_db
def test_empty_body_routes_reject_any_provided_key(
    api_client,
    authenticate,
    make_user,
    make_topic,
    make_quiz,
    make_quiz_question,
    make_quiz_answer,
):
    """Attempt start and submit accept an empty body only; a key is 422."""

    authenticate(api_client, make_user())
    quiz = make_quiz(make_topic())
    _add_question(make_quiz_question, make_quiz_answer, quiz, correct=1, wrong=1)

    rejected_start = api_client.post(
        ATTEMPT_START_URL.format(pk=quiz.pk),
        {"surprise": 1},
        format="json",
    )

    assert rejected_start.status_code == 422
    assert rejected_start.json()["code"] == "VALIDATION_ERROR"
    assert rejected_start.json()["fields"] == {"surprise": ["Unknown field."]}
    assert QuizAttempt.objects.count() == 0

    bodyless_start = api_client.post(ATTEMPT_START_URL.format(pk=quiz.pk))

    assert bodyless_start.status_code == 201

    attempt = bodyless_start.json()
    rejected_submit = api_client.post(
        ATTEMPT_SUBMIT_URL.format(pk=attempt["id"]),
        {"surprise": 1},
        format="json",
    )

    assert rejected_submit.status_code == 422
    assert rejected_submit.json()["fields"] == {"surprise": ["Unknown field."]}
    stored = QuizAttempt.objects.get(pk=attempt["id"])
    assert stored.status == QuizAttempt.Status.ACTIVE
    assert stored.score_percent is None


@pytest.mark.django_db
def test_attempt_detail_answers_options_and_head(
    api_client,
    authenticate,
    make_user,
    make_topic,
    make_quiz,
    make_quiz_question,
    make_quiz_answer,
):
    """``OPTIONS``/``HEAD`` must not raise a throttle-scope ``KeyError`` (500)."""

    authenticate(api_client, make_user())
    quiz = make_quiz(make_topic())
    _question, correct, _wrong = _add_question(
        make_quiz_question, make_quiz_answer, quiz, correct=1, wrong=1
    )
    attempt = _start(api_client, quiz)
    url = ATTEMPT_DETAIL_URL.format(pk=attempt["id"])

    options = api_client.options(url)
    head = api_client.head(url)

    assert options.status_code == 200
    assert head.status_code == 200
    assert _save(api_client, attempt["id"], [correct[0].pk]).status_code == 200


@pytest.mark.django_db
def test_attempt_start_is_throttled_by_the_attempt_scope(
    api_client,
    authenticate,
    make_user,
    make_topic,
    make_quiz,
    make_quiz_question,
    make_quiz_answer,
    monkeypatch,
):
    """The start route counts against ``learning_attempt`` and never creates twice."""

    monkeypatch.setattr(
        ScopedRateThrottle,
        "THROTTLE_RATES",
        {"learning_attempt": "2/min", "learning_read": "120/min"},
    )
    authenticate(api_client, make_user())
    quiz = make_quiz(make_topic())
    _add_question(make_quiz_question, make_quiz_answer, quiz, correct=1, wrong=1)
    url = ATTEMPT_START_URL.format(pk=quiz.pk)

    assert api_client.post(url, {}, format="json").status_code == 201
    assert api_client.post(url, {}, format="json").status_code == 200

    throttled = api_client.post(url, {}, format="json")

    assert throttled.status_code == 429
    assert throttled.json()["code"] == "THROTTLED"
    assert QuizAttempt.objects.count() == 1


@pytest.mark.django_db
def test_attempt_reads_and_writes_use_separate_throttle_scopes(
    api_client,
    authenticate,
    make_user,
    make_topic,
    make_quiz,
    make_quiz_question,
    make_quiz_answer,
    monkeypatch,
):
    """``GET`` is throttled by ``learning_read``, ``PATCH`` by ``learning_attempt``."""

    monkeypatch.setattr(
        ScopedRateThrottle,
        "THROTTLE_RATES",
        {"learning_attempt": "1/min", "learning_read": "120/min"},
    )
    user = make_user()
    authenticate(api_client, user)
    quiz = make_quiz(make_topic())
    question, correct, _wrong = _add_question(
        make_quiz_question, make_quiz_answer, quiz, correct=1, wrong=1
    )
    attempt = QuizAttempt.objects.create(
        user=user,
        quiz=quiz,
        question_ids=[question.pk],
        answers_state={"selected_answer_ids": []},
    )
    url = ATTEMPT_DETAIL_URL.format(pk=attempt.pk)

    assert api_client.get(url).status_code == 200
    assert _save(api_client, attempt.pk, [correct[0].pk]).status_code == 200

    throttled = _save(api_client, attempt.pk, [])

    assert throttled.status_code == 429
    assert throttled.json()["code"] == "THROTTLED"
    assert api_client.get(url).status_code == 200
    stored = QuizAttempt.objects.get(pk=attempt.pk)
    assert stored.answers_state == {"selected_answer_ids": [correct[0].pk]}


# ---------------------------------------------------------------------------
# Concurrency (real transactions).
#
# ``TransactionTestCase`` methods are unittest-style, so they cannot receive
# pytest fixtures: the graph and the authenticated client are built explicitly.
# ---------------------------------------------------------------------------


def _racing_user(username: str):
    user = User(username=username, role=User.Role.USER)
    user.set_unusable_password()
    user.save()
    return user


def _racing_client(user) -> APIClient:
    client = APIClient()
    access = RefreshToken.for_user(user).access_token
    access["auth_version"] = user.auth_version
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


def _racing_quiz():
    """A published demo topic with one quiz holding one two-answer question."""

    subject = Subject.objects.create(
        title="Pharmacology",
        slug="pharmacology",
        position=1,
    )
    section = Section.objects.create(
        subject=subject,
        title="Antibiotics",
        slug="antibiotics",
        position=1,
    )
    topic = Topic.objects.create(
        section=section,
        title="Beta-lactams",
        slug="beta-lactams",
        position=1,
        status=Topic.Status.PUBLISHED,
        access_level=Topic.AccessLevel.DEMO,
    )
    quiz = Quiz.objects.create(topic=topic, title="Racing", position=1)
    question = QuizQuestion.objects.create(quiz=quiz, text="Pick one", position=1)
    correct = QuizAnswer.objects.create(
        question=question,
        text="Correct",
        is_correct=True,
        position=1,
    )
    QuizAnswer.objects.create(question=question, text="Wrong", position=2)
    return quiz, question, correct


class ConcurrentStartTests(TransactionTestCase):
    """Two real transactions racing to start one attempt for the same quiz."""

    def test_concurrent_start_creates_one_attempt_and_one_conflict(self):
        user = _racing_user("racer")
        quiz, _question, _correct = _racing_quiz()
        barrier = threading.Barrier(2)
        find_active = services._find_active_attempt

        def synchronized_find(*args, **kwargs):
            # Both transactions see "no active attempt" before either inserts, so
            # the partial unique constraint (not scheduling luck) decides.
            found = find_active(*args, **kwargs)
            barrier.wait(timeout=10)
            return found

        def start(_index: int):
            try:
                client = _racing_client(user)
                response = client.post(
                    ATTEMPT_START_URL.format(pk=quiz.pk),
                    {},
                    format="json",
                )
                return response.status_code, response.json().get("code")
            finally:
                connections.close_all()

        with mock.patch.object(services, "_find_active_attempt", synchronized_find):
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(start, range(2)))

        self.assertEqual(sorted(status for status, _code in results), [201, 409])
        self.assertEqual(
            next(code for status, code in results if status == 409),
            "ACTIVE_ATTEMPT_EXISTS",
        )
        self.assertEqual(
            QuizAttempt.objects.filter(
                quiz=quiz,
                status=QuizAttempt.Status.ACTIVE,
            ).count(),
            1,
        )


class ConcurrentSubmitTests(TransactionTestCase):
    """Two real transactions submitting the same active attempt."""

    def test_concurrent_submit_freezes_the_score_once(self):
        user = _racing_user("submitter")
        quiz, question, correct = _racing_quiz()
        attempt = QuizAttempt.objects.create(
            user=user,
            quiz=quiz,
            question_ids=[question.pk],
            answers_state={"selected_answer_ids": [correct.pk]},
        )
        barrier = threading.Barrier(2)

        def submit(_index: int):
            try:
                client = _racing_client(user)
                barrier.wait(timeout=10)
                response = client.post(
                    ATTEMPT_SUBMIT_URL.format(pk=attempt.pk),
                    {},
                    format="json",
                )
                return response.status_code, response.json().get("code")
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(submit, range(2)))

        self.assertEqual(sorted(status for status, _code in results), [200, 409])
        self.assertEqual(
            next(code for status, code in results if status == 409),
            "ATTEMPT_ALREADY_SUBMITTED",
        )
        stored = QuizAttempt.objects.get(pk=attempt.pk)
        self.assertEqual(stored.status, QuizAttempt.Status.SUBMITTED)
        self.assertEqual(stored.score_percent, 100)
        self.assertIsNotNone(stored.submitted_at)
        self.assertEqual(
            stored.results,
            [
                {
                    "question_id": question.pk,
                    "selected_answer_ids": [correct.pk],
                    "correct_answer_ids": [correct.pk],
                    "score_percent": 100,
                }
            ],
        )
