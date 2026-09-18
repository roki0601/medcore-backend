from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .serializers import HealthResponseSerializer


@extend_schema(
    responses=HealthResponseSerializer,
    description="Liveness endpoint that does not depend on external services.",
)
@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    return Response({"service": "medcore-backend", "status": "ok"})
