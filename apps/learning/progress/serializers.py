"""Transport serializers for the topic progress sub-domain (feature 003)."""

from __future__ import annotations

from rest_framework import serializers

from apps.common.exceptions import APIError
from apps.learning.models import UserTopicProgress
from apps.learning.serializers import StrictSerializerMixin


class TopicProgressSerializer(serializers.Serializer):
    """The derived progress snapshot shared by every progress response."""

    topic = serializers.IntegerField()
    status = serializers.ChoiceField(choices=UserTopicProgress.Status.choices)
    theory_percent = serializers.IntegerField()
    completed_blocks = serializers.IntegerField()
    total_blocks = serializers.IntegerField()
    last_opened_at = serializers.DateTimeField(allow_null=True)
    started_at = serializers.DateTimeField(allow_null=True)
    completed_at = serializers.DateTimeField(allow_null=True)


class TopicProgressUpdateSerializer(StrictSerializerMixin, serializers.Serializer):
    """The ``PATCH`` body: ``{"opened": true}`` and/or ``{"status": "learned"}``.

    At least one field is required; ``learned`` is the only accepted status
    because the manual transition is the only status write this endpoint owns.
    """

    opened = serializers.BooleanField(required=False)
    status = serializers.ChoiceField(
        choices=[UserTopicProgress.Status.LEARNED],
        required=False,
    )

    def validate(self, attrs):
        if not attrs:
            raise APIError(
                "Request validation failed.",
                code="VALIDATION_ERROR",
                status_code=422,
                fields={"non_field_errors": ["At least one field is required."]},
            )
        return attrs
