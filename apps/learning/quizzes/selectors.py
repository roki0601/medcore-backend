"""Quiz and quiz-attempt reads for the learning API (feature 003).

The quiz list and detail expose two derived values — ``question_count`` and the
current user's ``best_score_percent`` — and never answer correctness. The attempt
reads restrict the visible questions to the frozen ``question_ids`` and hide
another user's attempt behind 404.
"""

from __future__ import annotations

from django.db.models import Count, Max, Q, QuerySet

from apps.common.exceptions import APIError
from apps.content.models import Quiz, QuizQuestion, Topic
from apps.learning.access import get_accessible_published_topic
from apps.learning.models import QuizAttempt


def _with_derived(user) -> QuerySet[Quiz]:
    """Quizzes annotated with the question count and the user's best score.

    ``best_score_percent`` is derived (never stored): the maximum stored score of
    the current user's submitted attempts of that quiz, ``null`` when there is
    none. The user/status restriction lives inside the aggregate filter so it
    cannot restrict which quizzes are listed.
    """

    return Quiz.objects.annotate(
        question_count=Count("questions", distinct=True),
        best_score_percent=Max(
            "attempts__score_percent",
            filter=Q(
                attempts__user=user,
                attempts__status=QuizAttempt.Status.SUBMITTED,
            ),
        ),
    )


def list_topic_quizzes(topic: Topic, user) -> QuerySet[Quiz]:
    """The quizzes of one topic in ``(position, id)`` order.

    The ordering is explicit: a grouped (aggregated) query drops the model's
    default ordering, so the paginated list must state it.
    """

    return _with_derived(user).filter(topic=topic).order_by("position", "id")


def get_quiz_with_derived(quiz_id: int, user) -> Quiz | None:
    """One annotated quiz with its questions and answers prefetched."""

    queryset = _with_derived(user).prefetch_related("questions__answers")
    return queryset.filter(pk=quiz_id).first()


def frozen_questions(attempt: QuizAttempt) -> list[QuizQuestion]:
    """The attempt's frozen question set as current content.

    The frozen ``question_ids`` order is authoritative for both the attempt
    payload and the grading breakdown, so a question repositioned or added after
    the start cannot reorder or extend an in-flight attempt. Quiz child IDs are
    stable by contract; a row that no longer exists is skipped defensively.
    """

    question_ids = [int(value) for value in (attempt.question_ids or [])]
    if not question_ids:
        return []
    queryset = QuizQuestion.objects.filter(
        quiz_id=attempt.quiz_id,
        pk__in=question_ids,
    ).prefetch_related("answers")
    by_id = {row.pk: row for row in queryset}
    return [by_id[question_id] for question_id in question_ids if question_id in by_id]


def get_owned_attempt(attempt_id: int, user) -> QuizAttempt:
    """Resolve one attempt owned by ``user`` on a published, accessible quiz.

    Another user's attempt is 404 ``RESOURCE_NOT_FOUND`` so its existence is not
    leaked, and the topic access decision is re-evaluated on every request.
    """

    attempt = (
        QuizAttempt.objects.select_related("quiz")
        .filter(
            pk=attempt_id,
            user=user,
        )
        .first()
    )
    if attempt is None:
        raise APIError(
            "Resource not found.",
            code="RESOURCE_NOT_FOUND",
            status_code=404,
        )
    get_accessible_published_topic(attempt.quiz.topic_id, user)
    return attempt
