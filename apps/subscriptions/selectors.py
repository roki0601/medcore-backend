from __future__ import annotations

from datetime import datetime
from typing import Any

from django.db.models import QuerySet
from django.utils import timezone

from .models import Plan, Subscription


def list_active_plans() -> QuerySet[Plan]:
    """Return all active subscription plans available to users."""
    return Plan.objects.filter(is_active=True).order_by(
        "price_rub", "duration_days", "id"
    )


def get_active_subscription(
    user: Any,
    *,
    at_time: datetime | None = None,
) -> Subscription | None:
    """Return the current active subscription granting paid entitlement, if any.

    A subscription grants entitlement if:
    - user is authenticated and active;
    - status is ACTIVE or CANCELLED;
    - starts_at <= at_time < expires_at.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    if not getattr(user, "is_active", True):
        return None

    current_time = at_time or timezone.now()
    return (
        Subscription.objects.select_related("plan")
        .filter(
            user=user,
            status__in=[Subscription.Status.ACTIVE, Subscription.Status.CANCELLED],
            starts_at__lte=current_time,
            expires_at__gt=current_time,
        )
        .order_by("-expires_at", "-id")
        .first()
    )


def get_current_or_latest_subscription(
    user: Any,
    *,
    at_time: datetime | None = None,
) -> Subscription | None:
    """Return user's active subscription if available, or latest subscription."""
    if user is None or not getattr(user, "is_authenticated", False):
        return None

    active = get_active_subscription(user, at_time=at_time)
    if active is not None:
        return active

    return (
        Subscription.objects.select_related("plan")
        .filter(user=user)
        .order_by("-expires_at", "-id")
        .first()
    )
