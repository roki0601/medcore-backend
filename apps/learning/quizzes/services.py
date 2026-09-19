"""Quiz attempt write use cases (feature 003).

Start freezes the quiz's current question set and moves the topic progress row to
``learning`` in the same transaction; save replaces the whole selection; submit
grades the frozen set and persists the result under a row lock, so a submitted
attempt is immutable. No pass flag is computed (the owner decision on a global
pass threshold is still open).
"""

from __future__ import annotations

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.common.exceptions import APIError
from apps.content.models import Quiz, QuizAnswer, QuizQuestion
from apps.learning.models import QuizAttempt
from apps.learning.quizzes.selectors import frozen_questions
from apps.learning.scoring import grade_attempt
from apps.learning.services import touch_topic_learning


def _active_attempt_exists() -> APIError:
    return APIError(
        "An active attempt already exists for this quiz.",
        code="ACTIVE_ATTEMPT_EXISTS",
        status_code=409,
    )


def _already_submitted() -> APIError:
    return APIError(
        "This attempt has already been submitted.",
        code="ATTEMPT_ALREADY_SUBMITTED",
        status_code=409,
    )


def _is_active_attempt_race(exc: IntegrityError) -> bool:
    """Whether the error chain is the one-active-attempt uniqueness race."""

    diagnostic = getattr(getattr(exc, "__cause__", None), "diag", None)
    return (
        getattr(diagnostic, "constraint_name", None)
        == "learning_quizattempt_unique_active_user_quiz"
    )


def _find_active_attempt(user, quiz: Quiz) -> QuizAttempt | None:
    """The user's active attempt for ``quiz``, locked for the start transaction."""

    queryset = QuizAttempt.objects.select_for_update().select_related("quiz")
    return queryset.filter(
        user=user,
        quiz=quiz,
        status=QuizAttempt.Status.ACTIVE,
    ).first()


def _freeze_question_ids(quiz: Quiz) -> list[int]:
    queryset = QuizQuestion.objects.filter(quiz=quiz).order_by("position", "id")
    return list(queryset.values_list("pk", flat=True))


def start_attempt(user, quiz: Quiz) -> tuple[QuizAttempt, bool]:
    """Return the user's active attempt for ``quiz`` and whether it was created.

    An existing active attempt is returned unchanged (200). Otherwise the attempt
    is created with the quiz's current question IDs frozen and an empty selection,
    and the topic progress row moves to ``learning`` in the same transaction
    (201). The loser of a concurrent start gets 409 ``ACTIVE_ATTEMPT_EXISTS``; the
    partial unique constraint is the backstop.
    """

    with transaction.atomic():
        existing = _find_active_attempt(user, quiz)
        if existing is not None:
            return existing, False
        question_ids = _freeze_question_ids(quiz)
        try:
            with transaction.atomic():
                attempt = QuizAttempt.objects.create(
                    user=user,
                    quiz=quiz,
                    question_ids=question_ids,
                    answers_state={"selected_answer_ids": []},
                )
        except IntegrityError as exc:
            if _is_active_attempt_race(exc):
                raise _active_attempt_exists() from exc
            raise
        touch_topic_learning(user, quiz.topic)
        return attempt, True


def save_attempt_answers(attempt: QuizAttempt, selected_answer_ids) -> QuizAttempt:
    """Replace the whole selection of one active attempt.

    Duplicates are collapsed, so retrying the same body is safe and idempotent.
    Every ID must be an answer of the attempt's quiz and belong to a question in
    the frozen ``question_ids``; otherwise 422 ``INVALID_ANSWER``. A submitted
    attempt is immutable: 409 ``ATTEMPT_ALREADY_SUBMITTED``.
    """

    selected = sorted({int(value) for value in selected_answer_ids})
    with transaction.atomic():
        queryset = QuizAttempt.objects.select_for_update().select_related("quiz")
        locked = queryset.get(pk=attempt.pk)
        if locked.status != QuizAttempt.Status.ACTIVE:
            raise _already_submitted()
        frozen = {int(value) for value in (locked.question_ids or [])}
        if selected:
            matched = QuizAnswer.objects.filter(
                pk__in=selected,
                question_id__in=frozen,
                question__quiz_id=locked.quiz_id,
            ).values_list("pk", flat=True)
            if len(set(matched)) != len(selected):
                raise APIError(
                    "One or more answers are not part of this attempt.",
                    code="INVALID_ANSWER",
                    status_code=422,
                    fields={"selected_answer_ids": ["Unknown answer id."]},
                )
        locked.answers_state = {"selected_answer_ids": selected}
        locked.save(update_fields=["answers_state", "updated_at"])
        return locked


def submit_attempt(attempt: QuizAttempt) -> QuizAttempt:
    """Grade and freeze one active attempt in a locked transaction.

    The frozen question set is graded against the current correctness flags of
    the content, and ``results``, ``score_percent`` and ``submitted_at`` are
    persisted; afterwards the attempt can never be rewritten. A concurrent second
    submit loses the row lock and gets 409 ``ATTEMPT_ALREADY_SUBMITTED``.
    """

    with transaction.atomic():
        queryset = QuizAttempt.objects.select_for_update().select_related("quiz")
        locked = queryset.get(pk=attempt.pk)
        if locked.status != QuizAttempt.Status.ACTIVE:
            raise _already_submitted()
        selected = (locked.answers_state or {}).get("selected_answer_ids") or []
        score_percent, results = grade_attempt(frozen_questions(locked), selected)
        locked.status = QuizAttempt.Status.SUBMITTED
        locked.results = results
        locked.score_percent = score_percent
        locked.submitted_at = timezone.now()
        locked.save(
            update_fields=[
                "status",
                "results",
                "score_percent",
                "submitted_at",
                "updated_at",
            ]
        )
        return locked
