from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import HttpResponse
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.exceptions import APIError
from apps.common.serializers import APIErrorResponseSerializer

from .robokassa import RobokassaConfigurationError
from .selectors import get_active_subscription, list_active_plans
from .serializers import (
    CreatePaymentRequestSerializer,
    CreatePaymentResponseSerializer,
    CurrentSubscriptionResponseSerializer,
    PaymentStatusResponseSerializer,
    PlanSerializer,
)
from .services import create_payment, process_robokassa_result

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
        active_sub = get_active_subscription(user)
        has_access = active_sub is not None

        response_data = {
            "has_access": has_access,
            "subscription": active_sub,
        }
        serializer = self.get_serializer(response_data)
        return Response(serializer.data)


class PaymentInitView(generics.GenericAPIView):
    """Initialize payment session and generate Robokassa checkout URL."""

    permission_classes = (IsAuthenticated,)

    serializer_class = CreatePaymentRequestSerializer
    throttle_scope = "subscriptions_payment"

    @extend_schema(
        summary="Initialize subscription payment",
        description=(
            "Creates a pending Payment order snapshotting the selected Plan price "
            "and returns a Robokassa checkout URL for buyer payment."
        ),
        request=CreatePaymentRequestSerializer,
        responses={
            201: CreatePaymentResponseSerializer,
            400: OpenApiResponse(
                response=APIErrorResponseSerializer,
                description="Validation error or plan not found (INVALID_REQUEST).",
            ),
            **ERROR_RESPONSES_401,
        },
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        plan_id = serializer.validated_data["plan_id"]

        try:
            payment, payment_url = create_payment(user=request.user, plan_id=plan_id)
        except DjangoValidationError as exc:
            field_errors = getattr(exc, "message_dict", None)
            if not field_errors and hasattr(exc, "messages"):
                field_errors = {"plan_id": exc.messages}
            raise DRFValidationError(
                field_errors or {"plan_id": ["Invalid plan."]}
            ) from exc
        except RobokassaConfigurationError as exc:
            raise APIError(
                detail="Платежный шлюз временно недоступен.",
                code="PAYMENT_PROVIDER_UNCONFIGURED",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            ) from exc

        response_data = {
            "payment_id": payment.id,
            "payment_url": payment_url,
            "amount": payment.amount,
            "status": payment.status,
        }
        return Response(
            CreatePaymentResponseSerializer(response_data).data,
            status=status.HTTP_201_CREATED,
        )


class RobokassaResultView(APIView):
    """Public webhook callback handler for Robokassa ResultURL notifications."""

    permission_classes = (AllowAny,)
    throttle_scope = "subscriptions_result"

    def _handle_notification(self, request):
        data = (
            request.data
            if request.method == "POST" and request.data
            else request.query_params
        )
        inv_id_raw = (
            data.get("InvId")
            or data.get("inv_id")
            or request.query_params.get("InvId")
            or request.query_params.get("inv_id")
        )
        out_sum_raw = (
            data.get("OutSum")
            or data.get("out_sum")
            or request.query_params.get("OutSum")
            or request.query_params.get("out_sum")
        )
        sig_raw = (
            data.get("SignatureValue")
            or data.get("signature_value")
            or data.get("crc")
            or request.query_params.get("SignatureValue")
            or request.query_params.get("signature_value")
            or request.query_params.get("crc")
        )

        if not (inv_id_raw and out_sum_raw and sig_raw):
            return HttpResponse(
                "bad request: missing parameters",
                content_type="text/plain",
                status=400,
            )

        try:
            inv_id = int(inv_id_raw)
        except (ValueError, TypeError):
            return HttpResponse(
                "bad request: invalid inv_id",
                content_type="text/plain",
                status=400,
            )

        success, message = process_robokassa_result(
            inv_id=inv_id,
            out_sum=str(out_sum_raw),
            signature=str(sig_raw),
        )

        if success:
            return HttpResponse(message, content_type="text/plain", status=200)
        return HttpResponse(
            f"bad request: {message}", content_type="text/plain", status=400
        )

    @extend_schema(
        summary="Robokassa ResultURL callback (POST)",
        description=(
            "Robokassa notification callback verifying payment completion. "
            "Activates subscription on valid payment and returns OK{InvId}."
        ),
        responses={
            200: OpenApiResponse(description="Notification accepted (OK{InvId})"),
            400: OpenApiResponse(description="Signature, invoice, or amount error"),
        },
    )
    def post(self, request, *args, **kwargs):
        return self._handle_notification(request)

    @extend_schema(
        summary="Robokassa ResultURL callback (GET)",
        description="Robokassa notification callback (GET fallback).",
        responses={
            200: OpenApiResponse(description="Notification accepted (OK{InvId})"),
            400: OpenApiResponse(description="Signature, invoice, or amount error"),
        },
    )
    def get(self, request, *args, **kwargs):
        return self._handle_notification(request)


class RobokassaSuccessView(APIView):
    """Buyer landing endpoint after successful payment (SuccessURL)."""

    permission_classes = (AllowAny,)
    throttle_scope = "subscriptions_read"

    @extend_schema(
        summary="Robokassa payment success redirect target",
        description="Buyer UX landing endpoint after completing payment at Robokassa.",
        responses={
            200: PaymentStatusResponseSerializer,
        },
    )
    def get(self, request, *args, **kwargs):
        return Response(
            {
                "status": "success",
                "message": "Оплата успешно завершена.",
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request, *args, **kwargs):
        return self.get(request, *args, **kwargs)


class RobokassaFailView(APIView):
    """Buyer landing endpoint after failed or cancelled payment (FailURL)."""

    permission_classes = (AllowAny,)
    throttle_scope = "subscriptions_read"

    @extend_schema(
        summary="Robokassa payment fail redirect target",
        description="Buyer UX landing endpoint after cancelled or failed payment.",
        responses={
            200: PaymentStatusResponseSerializer,
        },
    )
    def get(self, request, *args, **kwargs):
        return Response(
            {
                "status": "failed",
                "message": "Оплата отменена или не удалась.",
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request, *args, **kwargs):
        return self.get(request, *args, **kwargs)
