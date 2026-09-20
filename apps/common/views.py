import logging

from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.middleware.csrf import get_token
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .serializers import (
    CSRFTokenResponseSerializer,
    HealthReadinessResponseSerializer,
    HealthResponseSerializer,
)

logger = logging.getLogger(__name__)


@extend_schema(
    responses=CSRFTokenResponseSerializer,
    description=(
        "Bootstrap the CSRF cookie used by cookie-authenticated auth endpoints."
    ),
)
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def csrf_token(request):
    return Response({"csrf_token": get_token(request)})


def csrf_failure(request, reason: str = "") -> JsonResponse:
    del request, reason
    return JsonResponse(
        {
            "code": "CSRF_FAILED",
            "detail": "CSRF validation failed.",
            "fields": {},
        },
        status=403,
    )


@extend_schema(
    responses=HealthResponseSerializer,
    description="Liveness endpoint that does not depend on external services.",
)
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def health(request):
    return Response({"service": "medcore-backend", "status": "ok"})


@extend_schema(
    responses=HealthResponseSerializer,
    description="Liveness endpoint that does not depend on external services.",
)
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def health_live(request):
    return Response({"service": "medcore-backend", "status": "ok"})


@extend_schema(
    responses={
        200: HealthReadinessResponseSerializer,
        503: HealthReadinessResponseSerializer,
    },
    description="Readiness endpoint checking only the database and Redis cache.",
)
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def health_ready(request):
    checks = {"database": "ok", "cache": "ok"}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        checks["database"] = "unavailable"
        logger.exception("Readiness database check failed")

    try:
        cache.get("__medcore_readiness_probe__")
    except Exception:
        checks["cache"] = "unavailable"
        logger.exception("Readiness cache check failed")

    ready = all(value == "ok" for value in checks.values())
    return Response(
        {
            "service": "medcore-backend",
            "status": "ok" if ready else "unavailable",
            "checks": checks,
        },
        status=200 if ready else 503,
    )
