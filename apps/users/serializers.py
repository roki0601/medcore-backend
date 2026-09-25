from __future__ import annotations

import re
from collections.abc import Mapping

from rest_framework import serializers

from apps.common.exceptions import APIError
from apps.content.models import Subject

from .models import User, UserProfile
from .services import normalize_username


class TelegramLoginRequestSerializer(serializers.Serializer):
    id = serializers.IntegerField(min_value=1)
    auth_date = serializers.IntegerField(min_value=1)
    hash = serializers.CharField(min_length=64, max_length=64)
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)
    username = serializers.CharField(required=False, allow_blank=True)
    photo_url = serializers.CharField(required=False, allow_blank=True)

    def validate_hash(self, value: str) -> str:
        if not re.fullmatch(r"[0-9a-fA-F]{64}", value):
            raise serializers.ValidationError("Hash must be hexadecimal.")
        return value.lower()


class DevLoginRequestSerializer(serializers.Serializer):
    persona = serializers.ChoiceField(choices=["demo", "premium"])


class UserSummarySerializer(serializers.ModelSerializer):
    has_telegram = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "role",
            "has_telegram",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_has_telegram(self, obj: User) -> bool:
        return obj.telegram_id is not None


class UserUpdateSerializer(serializers.Serializer):
    username = serializers.CharField(required=True, allow_blank=True)

    def to_internal_value(self, data):
        if not isinstance(data, Mapping):
            return super().to_internal_value(data)
        unknown_fields = set(data) - {"username"}
        if unknown_fields:
            raise APIError(
                "Only username may be changed.",
                code="INVALID_REQUEST",
                status_code=400,
                fields={"unknown": sorted(unknown_fields)},
            )
        return super().to_internal_value(data)

    def validate_username(self, value: str) -> str:
        return normalize_username(value)


class DeleteAccountSerializer(serializers.Serializer):
    confirmation = serializers.CharField(required=True, allow_blank=False)

    def to_internal_value(self, data):
        if not isinstance(data, Mapping):
            return super().to_internal_value(data)
        unknown_fields = set(data) - {"confirmation"}
        if unknown_fields:
            raise APIError(
                "Only delete confirmation is accepted.",
                code="INVALID_REQUEST",
                status_code=400,
                fields={"unknown": sorted(unknown_fields)},
            )
        return super().to_internal_value(data)

    def validate_confirmation(self, value: str) -> str:
        if value != "DELETE":
            raise APIError(
                "Explicit delete confirmation is required.",
                code="INVALID_REQUEST",
                status_code=400,
                fields={"confirmation": ["Must equal DELETE."]},
            )
        return value


class AuthTokenResponseSerializer(serializers.Serializer):
    access_token = serializers.CharField()
    expires_in = serializers.IntegerField()
    user = UserSummarySerializer()


class RefreshTokenResponseSerializer(serializers.Serializer):
    access_token = serializers.CharField()
    expires_in = serializers.IntegerField()


class ProfileSubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ("id", "title", "slug")
        read_only_fields = fields


class UserProfileSerializer(serializers.ModelSerializer):
    selected_subjects = ProfileSubjectSerializer(many=True, read_only=True)

    class Meta:
        model = UserProfile
        fields = (
            "university",
            "course",
            "semester_goal",
            "daily_study_minutes",
            "selected_subjects",
        )
        read_only_fields = fields


class UserProfileUpdateSerializer(serializers.Serializer):
    university = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        max_length=255,
    )
    course = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=1,
        max_value=6,
    )
    semester_goal = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        max_length=255,
    )
    daily_study_minutes = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=1,
        max_value=1440,
    )
    selected_subject_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
    )
    selected_subjects = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
    )

    def to_internal_value(self, data):
        if not isinstance(data, Mapping):
            return super().to_internal_value(data)
        allowed_fields = {
            "university",
            "course",
            "semester_goal",
            "daily_study_minutes",
            "selected_subjects",
            "selected_subject_ids",
        }
        unknown_fields = set(data) - allowed_fields
        if unknown_fields:
            raise APIError(
                "Disallowed fields in profile update.",
                code="INVALID_REQUEST",
                status_code=400,
                fields={"unknown": sorted(unknown_fields)},
            )
        return super().to_internal_value(data)

    def validate(self, attrs):
        if "selected_subject_ids" in attrs and "selected_subjects" in attrs:
            message = "Send only one subject selection field."
            raise APIError(
                "Only one subject selection field may be provided.",
                code="INVALID_REQUEST",
                status_code=400,
                fields={
                    "selected_subject_ids": [message],
                    "selected_subjects": [message],
                },
            )

        subject_ids = None
        if "selected_subject_ids" in attrs:
            subject_ids = attrs["selected_subject_ids"]
        elif "selected_subjects" in attrs:
            subject_ids = attrs["selected_subjects"]

        if subject_ids is not None:
            unique_ids = list(dict.fromkeys(subject_ids))
            existing_ids = set(
                Subject.objects.filter(id__in=unique_ids).values_list("id", flat=True)
            )
            missing = [sid for sid in unique_ids if sid not in existing_ids]
            if missing:
                raise APIError(
                    f"Subject(s) with id {missing} do not exist.",
                    code="INVALID_REQUEST",
                    status_code=400,
                    fields={"selected_subjects": [f"Unknown subject ids: {missing}"]},
                )
            attrs["validated_subject_ids"] = unique_ids

        return attrs
