"""Flashcard API serializers (feature 003)."""

from __future__ import annotations

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.content.models import Flashcard
from apps.learning.flashcards.services import REVIEW_ACTIONS
from apps.learning.models import FlashcardReview
from apps.learning.serializers import StrictSerializerMixin


class FlashcardReviewStateSerializer(serializers.ModelSerializer):
    """The current user's scheduler state for one card, never the review history."""

    class Meta:
        model = FlashcardReview
        fields = ("interval_days", "repetitions", "last_reviewed_at", "next_review_at")


class FlashcardItemSerializer(serializers.ModelSerializer):
    """One flashcard with the requesting user's review state (``null`` if none)."""

    topic = serializers.IntegerField(source="topic_id", read_only=True)
    review = serializers.SerializerMethodField()

    class Meta:
        model = Flashcard
        fields = ("id", "topic", "question", "answer", "position", "review")

    @extend_schema_field(FlashcardReviewStateSerializer(allow_null=True))
    def get_review(self, obj: Flashcard):
        review = self.context.get("reviews", {}).get(obj.pk)
        if review is None:
            return None
        return FlashcardReviewStateSerializer(review).data


class DueFlashcardSerializer(serializers.ModelSerializer):
    """One due review row flattened to the flashcard item shape."""

    id = serializers.IntegerField(source="flashcard_id", read_only=True)
    topic = serializers.IntegerField(source="flashcard.topic_id", read_only=True)
    question = serializers.CharField(source="flashcard.question", read_only=True)
    answer = serializers.CharField(source="flashcard.answer", read_only=True)
    position = serializers.IntegerField(source="flashcard.position", read_only=True)
    review = FlashcardReviewStateSerializer(source="*", read_only=True)

    class Meta:
        model = FlashcardReview
        fields = ("id", "topic", "question", "answer", "position", "review")


class FlashcardReviewRequestSerializer(StrictSerializerMixin, serializers.Serializer):
    """The ``POST /flashcards/{id}/review/`` body."""

    action = serializers.ChoiceField(choices=REVIEW_ACTIONS)
