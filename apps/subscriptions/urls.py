from django.urls import path

from .views import CurrentSubscriptionView, PlanListView

urlpatterns = [
    path("subscriptions/plans/", PlanListView.as_view(), name="subscription-plan-list"),
    path(
        "subscriptions/current/",
        CurrentSubscriptionView.as_view(),
        name="subscription-current",
    ),
]
