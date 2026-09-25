import logging

from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.middleware.csrf import get_token
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Feedback
from .serializers import (
    CSRFTokenResponseSerializer,
    FeedbackCreateSerializer,
    FeedbackResponseSerializer,
    HealthReadinessResponseSerializer,
    HealthResponseSerializer,
)
from .throttles import FeedbackAnonThrottle, FeedbackUserThrottle

logger = logging.getLogger(__name__)


class FeedbackView(APIView):
    permission_classes = (AllowAny,)
    throttle_classes = (FeedbackAnonThrottle, FeedbackUserThrottle)

    @extend_schema(
        request=FeedbackCreateSerializer,
        responses={201: FeedbackResponseSerializer},
        description="Submit user feedback (authenticated or anonymous).",
    )
    def post(self, request):
        serializer = FeedbackCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user = request.user if request.user and request.user.is_authenticated else None
        topic_id = data.get("topic_id")

        feedback = Feedback.objects.create(
            user=user,
            type=data["type"],
            subject=data["subject"],
            message=data["message"],
            contact=data.get("contact", ""),
            page_url=data.get("page_url", ""),
            topic_id=topic_id,
        )

        response_serializer = FeedbackResponseSerializer(feedback)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


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
