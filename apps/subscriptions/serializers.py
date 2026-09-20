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
            "is_trial",
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
            "is_trial",
        )


class CurrentSubscriptionResponseSerializer(serializers.Serializer):
    has_access = serializers.BooleanField()
    subscription = CurrentSubscriptionSerializer(allow_null=True)
