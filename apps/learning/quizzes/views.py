"""Quiz and quiz-attempt views (feature 003).

Thin transport layer: resolve the published, accessible topic through the shared
access helpers, delegate the reads to the selectors and the writes to the
services, and render with the shared pagination and error envelope.
"""

from __future__ import annotations

from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.common.pagination import StandardPagination
from apps.common.serializers import APIErrorResponseSerializer
from apps.learning.access import get_accessible_published_topic, get_accessible_quiz
from apps.learning.quizzes.selectors import (
    get_owned_attempt,
    get_quiz_with_derived,
    list_topic_quizzes,
)
from apps.learning.quizzes.serializers import (
    QuizAttemptAnswersWriteSerializer,
    QuizAttemptSerializer,
    QuizDetailSerializer,
    TopicQuizSerializer,
)
from apps.learning.quizzes.services import (
    save_attempt_answers,
    start_attempt,
    submit_attempt,
)
from apps.learning.serializers import EmptyBodySerializer

READ_ERROR_RESPONSES = {
    400: OpenApiResponse(
        response=APIErrorResponseSerializer, description="Invalid request."
    ),
    401: OpenApiResponse(
        response=APIErrorResponseSerializer, description="Authentication required."
    ),
    403: OpenApiResponse(
        response=APIErrorResponseSerializer, description="Entitlement required."
    ),
    404: OpenApiResponse(
        response=APIErrorResponseSerializer, description="Resource not found."
    ),
    429: OpenApiResponse(
        response=APIErrorResponseSerializer, description="Too many requests."
    ),
}

WRITE_ERROR_RESPONSES = {
    **READ_ERROR_RESPONSES,
    409: OpenApiResponse(
        response=APIErrorResponseSerializer,
        description="Active attempt or submitted attempt conflict.",
    ),
    422: OpenApiResponse(
        response=APIErrorResponseSerializer, description="Invalid payload or answer id."
    ),
}


class TopicQuizListView(generics.GenericAPIView):
    permission_classes = (IsAuthenticated,)
    throttle_scope = "learning_read"
    pagination_class = StandardPagination
    serializer_class = TopicQuizSerializer

    @extend_schema(
        responses={200: TopicQuizSerializer(many=True), **READ_ERROR_RESPONSES},
        description=(
            "Paginated quizzes of one published, accessible topic in "
            "`(position, id)` order, each with `question_count` and the current "
            "user's derived `best_score_percent`. Scope: `learning_read`."
        ),
    )
    def get(self, request, topic_id: int):
        topic = get_accessible_published_topic(topic_id, request.user)
        page = self.paginate_queryset(list_topic_quizzes(topic, request.user))
        return self.get_paginated_response(self.get_serializer(page, many=True).data)


class QuizDetailView(generics.GenericAPIView):
    permission_classes = (IsAuthenticated,)
    throttle_scope = "learning_read"
    serializer_class = QuizDetailSerializer

    @extend_schema(
        responses={200: QuizDetailSerializer, **READ_ERROR_RESPONSES},
        description=(
            "One published, accessible quiz with its questions and answers in "
            "`(position, id)` order and the current user's derived "
            "`best_score_percent`. Answer correctness is never exposed here. "
            "Scope: `learning_read`."
        ),
    )
    def get(self, request, pk: int):
        quiz = get_accessible_quiz(pk, request.user)
        detail = get_quiz_with_derived(quiz.pk, request.user)
        return Response(self.get_serializer(detail).data)


class QuizAttemptStartView(generics.GenericAPIView):
    permission_classes = (IsAuthenticated,)
    throttle_scope = "learning_attempt"
    serializer_class = QuizAttemptSerializer

    @extend_schema(
        request=None,
        responses={
            201: QuizAttemptSerializer,
            200: QuizAttemptSerializer,
            **WRITE_ERROR_RESPONSES,
        },
        description=(
            "Start the current user's attempt of one published, accessible quiz: "
            "201 with a new attempt whose `question_ids` freeze the quiz's current "
            "questions in `(position, id)` order, or 200 with the existing active "
            "attempt. Starting also moves the topic progress row to `learning` in "
            "the same transaction. The racing loser of a concurrent start gets 409 "
            "`ACTIVE_ATTEMPT_EXISTS`. Scope: `learning_attempt`."
        ),
    )
    def post(self, request, pk: int):
        quiz = get_accessible_quiz(pk, request.user)
        EmptyBodySerializer(data=request.data).is_valid(raise_exception=True)
        attempt, created = start_attempt(request.user, quiz)
        return Response(
            self.get_serializer(attempt).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


@extend_schema_view(
    get=extend_schema(
        responses={200: QuizAttemptSerializer, **READ_ERROR_RESPONSES},
        description=(
            "One attempt owned by the current user; another user's attempt is 404 "
            "`RESOURCE_NOT_FOUND`. `questions` is the current content restricted to "
            "the frozen `question_ids` and never carries correctness while the "
            "attempt is active. Scope: `learning_read`."
        ),
    ),
    patch=extend_schema(
        request=QuizAttemptAnswersWriteSerializer,
        responses={200: QuizAttemptSerializer, **WRITE_ERROR_RESPONSES},
        description=(
            "Replace the whole selection of one active attempt (duplicates are "
            "collapsed, so retrying the same body is safe). Every ID must be an "
            "answer of the attempt's quiz and belong to a question in the frozen "
            "`question_ids`, otherwise 422 `INVALID_ANSWER`; a submitted attempt is "
            "409 `ATTEMPT_ALREADY_SUBMITTED`. Scope: `learning_attempt`."
        ),
    ),
)
class QuizAttemptDetailView(generics.GenericAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = QuizAttemptSerializer

    #: The two methods are throttled by different scopes; ``ScopedRateThrottle``
    #: reads ``throttle_scope`` from the view, so it is set per request before the
    #: throttle instances are built. ``HEAD`` is served by the ``GET`` handler and
    #: is therefore a read; any other method falls back to the write scope instead
    #: of raising a ``KeyError`` (500) on ``OPTIONS``.
    throttle_scopes = {
        "GET": "learning_read",
        "HEAD": "learning_read",
        "PATCH": "learning_attempt",
    }

    def get_throttles(self):
        self.throttle_scope = self.throttle_scopes.get(
            self.request.method,
            "learning_attempt",
        )
        return super().get_throttles()

    def get(self, request, pk: int):
        attempt = get_owned_attempt(pk, request.user)
        return Response(self.get_serializer(attempt).data)

    def patch(self, request, pk: int):
        attempt = get_owned_attempt(pk, request.user)
        serializer = QuizAttemptAnswersWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = save_attempt_answers(
            attempt,
            serializer.validated_data["selected_answer_ids"],
        )
        return Response(self.get_serializer(updated).data)


class QuizAttemptSubmitView(generics.GenericAPIView):
    permission_classes = (IsAuthenticated,)
    throttle_scope = "learning_attempt"
    serializer_class = QuizAttemptSerializer

    @extend_schema(
        request=None,
        responses={200: QuizAttemptSerializer, **WRITE_ERROR_RESPONSES},
        description=(
            "Submit one active attempt owned by the current user: the frozen "
            "question set is graded against the current content, and `results`, "
            "`score_percent` and `submitted_at` are persisted under a row lock. No "
            "pass flag is computed. A repeated or concurrent submit gets 409 "
            "`ATTEMPT_ALREADY_SUBMITTED`. Scope: `learning_attempt`."
        ),
    )
    def post(self, request, pk: int):
        attempt = get_owned_attempt(pk, request.user)
        EmptyBodySerializer(data=request.data).is_valid(raise_exception=True)
        return Response(self.get_serializer(submit_attempt(attempt)).data)
