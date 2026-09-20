"""HTTP layer for the user learning dashboard (feature 007)."""

from __future__ import annotations

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.common.serializers import APIErrorResponseSerializer
from apps.learning.dashboard.selectors import get_user_dashboard
from apps.learning.dashboard.serializers import DashboardResponseSerializer


class DashboardView(generics.GenericAPIView):
    """Aggregate learning progress and activity dashboard for the authenticated user."""

    permission_classes = (IsAuthenticated,)
    serializer_class = DashboardResponseSerializer
    pagination_class = None

    def get_throttles(self):
        self.throttle_scope = "learning_read"
        return super().get_throttles()

    @extend_schema(
        request=None,
        responses={
            200: DashboardResponseSerializer,
            401: OpenApiResponse(
                response=APIErrorResponseSerializer,
                description="Authentication required (AUTHENTICATION_REQUIRED).",
            ),
            429: OpenApiResponse(
                response=APIErrorResponseSerializer,
                description="Too many requests (THROTTLED).",
            ),
        },
        summary="User learning dashboard",
        description=(
            "Aggregated learning state and summary for the authenticated user's "
            "started topics. Shows only topics where user activity exists. "
            "Re-verifies topic access policy. Throttle scope: learning_read."
        ),
    )
    def get(self, request):
        dashboard_data = get_user_dashboard(request.user)
        return Response(self.get_serializer(dashboard_data).data)
