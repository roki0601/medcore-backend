from rest_framework import serializers


class APIErrorResponseSerializer(serializers.Serializer):
    code = serializers.CharField()
    detail = serializers.CharField()
    fields = serializers.DictField()


class HealthResponseSerializer(serializers.Serializer):
    service = serializers.CharField()
    status = serializers.CharField()


class HealthReadinessResponseSerializer(HealthResponseSerializer):
    checks = serializers.DictField(child=serializers.CharField())


class CSRFTokenResponseSerializer(serializers.Serializer):
    csrf_token = serializers.CharField()


class FeedbackCreateSerializer(serializers.Serializer):
    type = serializers.ChoiceField(
        choices=[
            "content_error",
            "new_topic",
            "new_subject",
            "suggestion",
            "technical_issue",
            "other",
        ]
    )
    subject = serializers.CharField(max_length=255, trim_whitespace=True, min_length=1)
    message = serializers.CharField(max_length=5000, trim_whitespace=True, min_length=5)
    contact = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
        default="",
    )
    page_url = serializers.CharField(
        max_length=500,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
        default="",
    )
    topic_id = serializers.IntegerField(required=False, allow_null=True, default=None)

    def validate_subject(self, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise serializers.ValidationError("Subject cannot be empty.")
        return trimmed

    def validate_message(self, value: str) -> str:
        trimmed = value.strip()
        if len(trimmed) < 5:
            raise serializers.ValidationError(
                "Message must be at least 5 characters long."
            )
        return trimmed

    def validate_topic_id(self, value: int | None) -> int | None:
        if value is not None:
            from apps.content.models import Topic

            if not Topic.objects.filter(pk=value).exists():
                raise serializers.ValidationError("Topic does not exist.")
        return value


class FeedbackResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    status = serializers.CharField()
    created_at = serializers.DateTimeField()
