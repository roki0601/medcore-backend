"""URL routing for the dashboard sub-domain (feature 007)."""

from __future__ import annotations

from django.urls import path

from apps.learning.dashboard.views import DashboardView

urlpatterns = [
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
]
