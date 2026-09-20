from __future__ import annotations

from rest_framework import serializers

from .models import Plan, Subscription


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = (
            "id",
            "code",
            "title",
            "description",
            "price_rub",
            "duration_days",
        )


class SubscriptionPlanSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = (
            "id",
            "code",
            "title",
            "duration_days",
        )


class CurrentSubscriptionSerializer(serializers.ModelSerializer):
    plan = SubscriptionPlanSummarySerializer(read_only=True)

    class Meta:
        model = Subscription
        fields = (
            "id",
            "plan",
            "status",
            "starts_at",
            "expires_at",
        )


class CurrentSubscriptionResponseSerializer(serializers.Serializer):
    has_access = serializers.BooleanField()
    subscription = CurrentSubscriptionSerializer(allow_null=True)


class CreatePaymentRequestSerializer(serializers.Serializer):
    plan_id = serializers.IntegerField(
        min_value=1,
        help_text="ID активного плана подписки для покупки.",
    )


class CreatePaymentResponseSerializer(serializers.Serializer):
    payment_id = serializers.IntegerField(help_text="ID созданного платежа (InvId).")
    payment_url = serializers.CharField(
        help_text="URL для перенаправления покупателя на оплату в Robokassa."
    )

    amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Сумма к оплате в рублях.",
    )
    status = serializers.CharField(help_text="Текущий статус платежа (pending).")


class PaymentStatusResponseSerializer(serializers.Serializer):
    status = serializers.CharField(help_text="Статус операции (success / failed).")
    message = serializers.CharField(
        help_text="Пользовательское сообщение о результате."
    )
