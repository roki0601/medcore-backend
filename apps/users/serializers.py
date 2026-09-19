from __future__ import annotations

import re
from collections.abc import Mapping

from rest_framework import serializers

from apps.common.exceptions import APIError

from .models import User
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
    user = UserSummarySerializer(required=False)


class RefreshTokenResponseSerializer(serializers.Serializer):
    access_token = serializers.CharField()
    expires_in = serializers.IntegerField()
