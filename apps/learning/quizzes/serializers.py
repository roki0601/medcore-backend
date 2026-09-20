"""Quiz and quiz-attempt serializers (feature 003).

The read payloads never carry answer correctness: the quiz detail and an active
attempt expose question/answer IDs, text and position only. A submitted attempt
additionally exposes the frozen graded ``results``, which contain IDs and numeric
scores and are the only correctness signal the API ever emits.
"""

from __future__ import annotations

from drf_spectacular.utils import extend_schema_field, extend_schema_serializer
from rest_framework import serializers

from apps.content.models import Quiz, QuizAnswer, QuizQuestion
from apps.learning.models import QuizAttempt
from apps.learning.quizzes.selectors import frozen_questions
from apps.learning.serializers import StrictSerializerMixin

#: Transport bound for one attempt selection: the frozen question set of a single
#: quiz is far smaller than this, so a longer list is a malformed payload and must
#: fail validation (422) instead of reaching the driver.
MAX_SELECTED_ANSWER_IDS = 500


class QuizAnswerReadSerializer(serializers.ModelSerializer):
    """One answer without ``is_correct``: correctness is never exposed here."""

    class Meta:
        model = QuizAnswer
        fields = ("id", "text", "position")


class QuizQuestionReadSerializer(serializers.ModelSerializer):
    answers = QuizAnswerReadSerializer(many=True, read_only=True)

    class Meta:
        model = QuizQuestion
        fields = ("id", "text", "position", "answers")


class TopicQuizSerializer(serializers.ModelSerializer):
    """One quiz of the topic list with the user's derived best score."""

    topic = serializers.IntegerField(source="topic_id", read_only=True)
    question_count = serializers.IntegerField(read_only=True)
    best_score_percent = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = Quiz
        fields = (
            "id",
            "topic",
            "title",
            "description",
            "position",
            "question_count",
            "best_score_percent",
        )


# ``content`` already owns a ``QuizDetail`` component for the authoring API, so
# without an explicit name the learning response schema would resolve to that
# component (the wrong shape) instead of this one.
@extend_schema_serializer(component_name="TopicQuizDetail")
class QuizDetailSerializer(TopicQuizSerializer):
    questions = QuizQuestionReadSerializer(many=True, read_only=True)

    class Meta(TopicQuizSerializer.Meta):
        fields = TopicQuizSerializer.Meta.fields + ("questions",)


class QuizAttemptResultSerializer(serializers.Serializer):
    question_id = serializers.IntegerField()
    selected_answer_ids = serializers.ListField(child=serializers.IntegerField())
    correct_answer_ids = serializers.ListField(child=serializers.IntegerField())
    score_percent = serializers.IntegerField()


class QuizAttemptSerializer(serializers.ModelSerializer):
    """One attempt with its frozen question set and no correctness leak."""

    topic = serializers.IntegerField(source="quiz.topic_id", read_only=True)
    question_ids = serializers.ListField(
        child=serializers.IntegerField(),
        read_only=True,
    )
    selected_answer_ids = serializers.SerializerMethodField()
    questions = serializers.SerializerMethodField()
    results = QuizAttemptResultSerializer(
        many=True,
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = QuizAttempt
        fields = (
            "id",
            "quiz",
            "topic",
            "status",
            "question_ids",
            "selected_answer_ids",
            "questions",
            "results",
            "score_percent",
            "started_at",
            "submitted_at",
            "updated_at",
        )

    def get_selected_answer_ids(self, obj: QuizAttempt) -> list[int]:
        return list((obj.answers_state or {}).get("selected_answer_ids") or [])

    @extend_schema_field(QuizQuestionReadSerializer(many=True))
    def get_questions(self, obj: QuizAttempt) -> list[dict]:
        return QuizQuestionReadSerializer(frozen_questions(obj), many=True).data


class QuizAttemptAnswersWriteSerializer(StrictSerializerMixin, serializers.Serializer):
    """``PATCH /quiz-attempts/{id}/``: the whole replacement selection.

    An empty list is valid (it clears the selection); an unknown field is 422
    ``VALIDATION_ERROR`` through the shared strict-write mixin. The selection can
    never be longer than the frozen question set of one quiz, so a larger list is
    a malformed payload (422) rather than a driver-level failure.
    """

    selected_answer_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=True,
        max_length=MAX_SELECTED_ANSWER_IDS,
    )
