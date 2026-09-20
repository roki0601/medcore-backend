from __future__ import annotations

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.common.serializers import APIErrorResponseSerializer

from .policy import has_paid_content_entitlement
from .selectors import get_active_subscription, list_active_plans
from .serializers import (
    CurrentSubscriptionResponseSerializer,
    PlanSerializer,
)

ERROR_RESPONSES_401 = {
    401: OpenApiResponse(
        response=APIErrorResponseSerializer,
        description="Authentication required (AUTHENTICATION_REQUIRED).",
    ),
    429: OpenApiResponse(
        response=APIErrorResponseSerializer,
        description="Too many requests (THROTTLED).",
    ),
}

ERROR_RESPONSES_PUBLIC = {
    429: OpenApiResponse(
        response=APIErrorResponseSerializer,
        description="Too many requests (THROTTLED).",
    ),
}


class PlanListView(generics.ListAPIView):
    """Return all active subscription plans available for purchase."""

    permission_classes = (AllowAny,)
    serializer_class = PlanSerializer
    pagination_class = None
    throttle_scope = "subscriptions_read"

    def get_queryset(self):
        return list_active_plans()

    @extend_schema(
        summary="List active subscription plans",
        description=(
            "Returns all subscription plans available to purchase, "
            "ordered by price and duration."
        ),
        responses={
            200: PlanSerializer(many=True),
            **ERROR_RESPONSES_PUBLIC,
        },
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class CurrentSubscriptionView(generics.GenericAPIView):
    """Return authenticated user's paid entitlement status and active subscription."""

    permission_classes = (IsAuthenticated,)
    serializer_class = CurrentSubscriptionResponseSerializer
    pagination_class = None
    throttle_scope = "subscriptions_read"

    @extend_schema(
        summary="Get current user subscription and access",
        description=(
            "Returns whether the user currently holds active paid content entitlement "
            "and the details of their active subscription, if any."
        ),
        responses={
            200: CurrentSubscriptionResponseSerializer,
            **ERROR_RESPONSES_401,
        },
    )
    def get(self, request, *args, **kwargs):
        user = request.user
        has_access = has_paid_content_entitlement(user)
        active_sub = get_active_subscription(user)

        response_data = {
            "has_access": has_access,
            "subscription": active_sub,
        }
        serializer = self.get_serializer(response_data)
        return Response(serializer.data)
