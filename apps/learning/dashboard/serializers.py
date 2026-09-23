"""Serializers for the user learning dashboard (feature 007)."""

from __future__ import annotations

from rest_framework import serializers

from apps.learning.models import UserTopicProgress


class DashboardSummarySerializer(serializers.Serializer):
    """Aggregated counters across all accessible started topics."""

    started_topics_count = serializers.IntegerField(min_value=0)
    completed_theory_topics_count = serializers.IntegerField(min_value=0)
    flashcards_due_count = serializers.IntegerField(min_value=0)
    quizzes_attempted_count = serializers.IntegerField(min_value=0)


class DashboardSubjectSerializer(serializers.Serializer):
    """Compact subject metadata for dashboard topic items."""

    id = serializers.IntegerField()
    title = serializers.CharField()
    slug = serializers.CharField()


class DashboardSectionSerializer(serializers.Serializer):
    """Compact section metadata for dashboard topic items."""

    id = serializers.IntegerField()
    title = serializers.CharField()


class DashboardTheorySerializer(serializers.Serializer):
    """Canonical theory progress for one topic."""

    status = serializers.ChoiceField(choices=UserTopicProgress.Status.choices)
    progress_percent = serializers.IntegerField(min_value=0, max_value=100)


class DashboardFlashcardsSerializer(serializers.Serializer):
    """Due flashcards count for one topic."""

    due_count = serializers.IntegerField(min_value=0)


class DashboardQuizSerializer(serializers.Serializer):
    """Aggregated quiz status and best score from submitted attempts."""

    attempted = serializers.BooleanField()
    best_score_percent = serializers.IntegerField(
        min_value=0,
        max_value=100,
        allow_null=True,
    )


class DashboardTopicItemSerializer(serializers.Serializer):
    """One started topic with its theory, flashcard, and quiz aggregates."""

    id = serializers.IntegerField()
    title = serializers.CharField()
    slug = serializers.CharField()
    subject = DashboardSubjectSerializer()
    section = DashboardSectionSerializer()
    theory = DashboardTheorySerializer()
    flashcards = DashboardFlashcardsSerializer()
    quiz = DashboardQuizSerializer()
    last_activity_at = serializers.DateTimeField()


class DashboardResponseSerializer(serializers.Serializer):
    """Top-level envelope for GET /api/v1/dashboard/."""

    summary = DashboardSummarySerializer()
    topics = DashboardTopicItemSerializer(many=True)
