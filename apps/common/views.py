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

from .serializers import CSRFTokenResponseSerializer, HealthResponseSerializer


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
@permission_classes([AllowAny])
def health(request):
    return Response({"service": "medcore-backend", "status": "ok"})
