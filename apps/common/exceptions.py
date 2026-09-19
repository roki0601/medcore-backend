from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from rest_framework import status
from rest_framework.exceptions import (
    APIException,
    AuthenticationFailed,
    NotAuthenticated,
    NotFound,
    ParseError,
    PermissionDenied,
    Throttled,
    ValidationError,
)
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler
from rest_framework.views import set_rollback


class APIError(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Request failed."
    default_code = "INVALID_REQUEST"

    def __init__(
        self,
        detail: str,
        *,
        code: str,
        status_code: int,
        fields: Mapping[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self.default_detail = detail
        self.default_code = code
        self.fields = dict(fields or {})
        super().__init__(detail=detail, code=code)


def _error_fields(data: Any) -> dict[str, Any]:
    if isinstance(data, Mapping):
        return dict(data)
    if isinstance(data, list):
        return {"non_field_errors": data}
    return {}


def _nested_error_code(exc: Exception) -> str | None:
    detail = getattr(exc, "detail", None)
    if isinstance(detail, Mapping):
        detail_code = detail.get("code")
        if detail_code:
            return str(detail_code)
    if not hasattr(exc, "get_codes"):
        return None
    codes = exc.get_codes()
    if isinstance(codes, Mapping):
        nested_code = codes.get("code")
        return str(nested_code) if nested_code else None
    return str(codes) if codes else None


def _error_code(exc: Exception, response: Response) -> str:
    if isinstance(exc, APIError):
        return exc.default_code
    if isinstance(exc, Throttled):
        return "THROTTLED"
    if isinstance(exc, (AuthenticationFailed, NotAuthenticated)):
        known_codes = {"AUTH_USER_INACTIVE", "AUTH_REFRESH_REVOKED"}
        nested_code = _nested_error_code(exc)
        if nested_code in known_codes:
            return nested_code
        return "AUTHENTICATION_REQUIRED"
    if isinstance(exc, ValidationError):
        return "INVALID_REQUEST"
    if isinstance(exc, NotFound):
        return "RESOURCE_NOT_FOUND"
    if isinstance(exc, ParseError):
        return "INVALID_REQUEST"
    if response.status_code == status.HTTP_401_UNAUTHORIZED:
        return "AUTHENTICATION_REQUIRED"
    if response.status_code == status.HTTP_403_FORBIDDEN:
        return "PERMISSION_DENIED"
    return "REQUEST_FAILED"


def _error_detail(exc: Exception, response: Response) -> str:
    if isinstance(exc, APIError):
        return str(exc.detail)
    if isinstance(exc, Throttled):
        return "Too many requests."
    if isinstance(exc, (AuthenticationFailed, NotAuthenticated)):
        nested_code = _nested_error_code(exc)
        if nested_code == "AUTH_USER_INACTIVE":
            return "User account is inactive."
        if nested_code == "AUTH_REFRESH_REVOKED":
            return "Refresh session is invalid or revoked."
        return "Authentication credentials were invalid or missing."
    if isinstance(exc, PermissionDenied):
        return "You do not have permission to perform this action."
    if isinstance(exc, NotFound):
        return "Resource not found."
    if isinstance(exc, ValidationError):
        return "Request validation failed."
    if isinstance(exc, ParseError):
        return "Request body is invalid."
    return "Request failed."


def exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    if isinstance(exc, APIError):
        fields = exc.fields
    elif isinstance(exc, ValidationError):
        fields = _error_fields(response.data)
    else:
        fields = {}

    response.data = {
        "code": _error_code(exc, response),
        "detail": _error_detail(exc, response),
        "fields": fields,
    }
    set_rollback()
    return response
