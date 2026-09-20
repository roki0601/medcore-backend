from django.urls import path

from .views import (
    CurrentSubscriptionView,
    PaymentInitView,
    PlanListView,
    RobokassaFailView,
    RobokassaResultView,
    RobokassaSuccessView,
)

urlpatterns = [
    path("subscriptions/plans/", PlanListView.as_view(), name="subscription-plan-list"),
    path(
        "subscriptions/current/",
        CurrentSubscriptionView.as_view(),
        name="subscription-current",
    ),
    path(
        "subscriptions/payments/",
        PaymentInitView.as_view(),
        name="subscription-payment-init",
    ),
    path(
        "subscriptions/payments/robokassa/result/",
        RobokassaResultView.as_view(),
        name="subscription-robokassa-result",
    ),
    path(
        "subscriptions/payments/robokassa/success/",
        RobokassaSuccessView.as_view(),
        name="subscription-robokassa-success",
    ),
    path(
        "subscriptions/payments/robokassa/fail/",
        RobokassaFailView.as_view(),
        name="subscription-robokassa-fail",
    ),
]
