"""Transport primitives shared by the learning API serializers (feature 003)."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.common.exceptions import APIError


def _validation_fields(exc: serializers.ValidationError) -> dict[str, Any]:
    detail = exc.detail
    if isinstance(detail, dict):
        return {str(key): value for key, value in detail.items()}
    if isinstance(detail, list):
        return {"non_field_errors": detail}
    return {"non_field_errors": [detail]}


class StrictSerializerMixin:
    """Reject unknown keys and report failures in the learning API envelope.

    DRF ignores unknown keys by default and reports its own ``ValidationError``
    as HTTP 400 ``INVALID_REQUEST``; the learning API contract requires 422
    ``VALIDATION_ERROR`` with the offending keys in ``fields``.
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


class EmptyBodySerializer(StrictSerializerMixin, serializers.Serializer):
    """An empty write body: every provided JSON key is an unknown field.

    The three empty-body routes (theory-block completion, attempt start and
    attempt submit) validate ``request.data`` with it, so the contract's "unknown
    JSON fields in any write body → 422 ``VALIDATION_ERROR``" holds for them too.
    An empty body and ``{}`` stay valid.
    """
