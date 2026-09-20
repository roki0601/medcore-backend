from __future__ import annotations

from django.core.exceptions import RequestDataTooBig
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin


class APIRequestDataTooBigMiddleware(MiddlewareMixin):
    """Keep oversized API requests inside the canonical JSON error contract."""

    def process_exception(self, request, exception):
        if not isinstance(exception, RequestDataTooBig):
            return None
        if not request.path.startswith("/api/"):
            return None
        return JsonResponse(
            {
                "code": "INVALID_REQUEST",
                "detail": "Request body is too large.",
                "fields": {},
            },
            status=400,
        )
