from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from rest_framework import serializers

from apps.common.exceptions import APIError
from apps.media.models import MediaFile

ORIGINAL_NAME_MAX_LENGTH = 255
CHECKSUM_MAX_LENGTH = 128


def _validation_fields(exc: serializers.ValidationError) -> dict[str, Any]:
    detail = exc.detail
    if isinstance(detail, Mapping):
        return {str(key): value for key, value in detail.items()}
    if isinstance(detail, list):
        return {"non_field_errors": detail}
    return {"non_field_errors": [detail]}


class StrictMediaSerializerMixin:
    """Reject unknown keys and report failures in the API envelope.

    DRF ignores unknown keys by default and reports its own ``ValidationError``
    as HTTP 400 ``INVALID_REQUEST``; the media API contract requires 422
    ``VALIDATION_ERROR`` naming the offending keys.
    """

    def to_internal_value(self, data):
        if hasattr(data, "keys"):
            unknown = [key for key in data.keys() if key not in self.fields]
            if unknown:
                raise APIError(
                    "Request validation failed.",
                    code="VALIDATION_ERROR",
                    status_code=422,
                    fields={str(key): ["Unknown field."] for key in unknown},
                )
        return super().to_internal_value(data)

    def run_validation(self, data=serializers.empty):
        try:
            return super().run_validation(data)
        except APIError:
            raise
        except serializers.ValidationError as exc:
            raise APIError(
                "Request validation failed.",
                code="VALIDATION_ERROR",
                status_code=422,
                fields=_validation_fields(exc),
            ) from exc


class MediaWriteSerializer(StrictMediaSerializerMixin, serializers.Serializer):
    """The metadata payload of ``POST /api/v1/media/`` (no binary content).

    ``mime_type`` and ``size_bytes`` are re-checked against the configured
    allow-list and upload limit by the service, which reports 422
    ``MEDIA_INVALID``; this serializer owns only the payload shape.
    """

    original_name = serializers.CharField(
        max_length=ORIGINAL_NAME_MAX_LENGTH,
        required=False,
        allow_blank=True,
        default="",
    )
    mime_type = serializers.CharField(max_length=127)
    size_bytes = serializers.IntegerField(min_value=1)
    checksum = serializers.CharField(
        max_length=CHECKSUM_MAX_LENGTH,
        required=False,
        allow_blank=True,
        default="",
    )
    visibility = serializers.ChoiceField(
        choices=MediaFile.Visibility.choices,
        default=MediaFile.Visibility.PROTECTED.value,
    )


class MediaSerializer(serializers.ModelSerializer):
    """The client representation of one media row; never its ``storage_key``."""

    class Meta:
        model = MediaFile
        fields = (
            "id",
            "original_name",
            "mime_type",
            "size_bytes",
            "checksum",
            "visibility",
            "created_at",
            "updated_at",
        )


class UploadUrlSerializer(serializers.Serializer):
    """The upload contract issued for one media row."""

    upload_url = serializers.CharField(source="url")
    method = serializers.CharField()
    expires_at = serializers.DateTimeField()


class AccessUrlSerializer(serializers.Serializer):
    """The short-lived read URL issued for one media row."""

    access_url = serializers.CharField(source="url")
    method = serializers.CharField()
    expires_at = serializers.DateTimeField()
