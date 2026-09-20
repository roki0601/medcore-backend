from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.subscriptions.models import Plan, Subscription

User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def monthly_plan(db):
    return Plan.objects.create(
        code="monthly",
        title="Месячная подписка",
        description="Полный доступ на месяц",
        price_rub=Decimal("990.00"),
        duration_days=30,
        is_active=True,
    )


@pytest.fixture
def yearly_plan(db):
    return Plan.objects.create(
        code="yearly",
        title="Годовая подписка",
        description="Полный доступ на год",
        price_rub=Decimal("7990.00"),
        duration_days=365,
        is_active=True,
    )


@pytest.fixture
def inactive_plan(db):
    return Plan.objects.create(
        code="old-plan",
        title="Архивный тариф",
        description="Недоступен",
        price_rub=Decimal("500.00"),
        duration_days=30,
        is_active=False,
    )


@pytest.mark.django_db
def test_plans_list_is_public_and_excludes_inactive(
    api_client, monthly_plan, yearly_plan, inactive_plan
):
    response = api_client.get("/api/v1/subscriptions/plans/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2

    codes = [p["code"] for p in data]
    assert codes == ["monthly", "yearly"]
    assert "old-plan" not in codes

    first = data[0]
    assert first["code"] == "monthly"
    assert first["title"] == "Месячная подписка"
    assert first["price_rub"] == "990.00"
    assert first["duration_days"] == 30


@pytest.mark.django_db
def test_current_subscription_unauthenticated_returns_401(api_client):
    response = api_client.get("/api/v1/subscriptions/current/")
    assert response.status_code == 401
    assert response.json()["code"] == "AUTHENTICATION_REQUIRED"


@pytest.mark.django_db
def test_current_subscription_user_without_subscription(api_client):
    user = User.objects.create_user(username="free_user")
    api_client.force_authenticate(user=user)

    response = api_client.get("/api/v1/subscriptions/current/")
    assert response.status_code == 200
    data = response.json()
    assert data["has_access"] is False
    assert data["subscription"] is None


@pytest.mark.django_db
def test_current_subscription_user_with_active_subscription(api_client, monthly_plan):
    user = User.objects.create_user(username="paid_user")
    now = timezone.now()
    sub = Subscription.objects.create(
        user=user,
        plan=monthly_plan,
        status=Subscription.Status.ACTIVE,
        starts_at=now - timedelta(days=1),
        expires_at=now + timedelta(days=29),
    )
    api_client.force_authenticate(user=user)

    response = api_client.get("/api/v1/subscriptions/current/")
    assert response.status_code == 200
    data = response.json()
    assert data["has_access"] is True
    assert data["subscription"] is not None
    assert data["subscription"]["id"] == sub.id
    assert data["subscription"]["status"] == "active"
    assert data["subscription"]["plan"]["code"] == "monthly"


@pytest.mark.django_db
def test_current_subscription_cancelled_within_period_has_access(
    api_client, monthly_plan
):
    user = User.objects.create_user(username="cancelling_user")
    now = timezone.now()
    sub = Subscription.objects.create(
        user=user,
        plan=monthly_plan,
        status=Subscription.Status.CANCELLED,
        starts_at=now - timedelta(days=5),
        expires_at=now + timedelta(days=25),
    )
    api_client.force_authenticate(user=user)

    response = api_client.get("/api/v1/subscriptions/current/")
    assert response.status_code == 200
    data = response.json()
    assert data["has_access"] is True
    assert data["subscription"]["id"] == sub.id
    assert data["subscription"]["status"] == "cancelled"


@pytest.mark.django_db
def test_current_subscription_expired_has_no_access(api_client, monthly_plan):
    user = User.objects.create_user(username="expired_user")
    now = timezone.now()
    Subscription.objects.create(
        user=user,
        plan=monthly_plan,
        status=Subscription.Status.ACTIVE,
        starts_at=now - timedelta(days=60),
        expires_at=now - timedelta(days=30),
    )
    api_client.force_authenticate(user=user)

    response = api_client.get("/api/v1/subscriptions/current/")
    assert response.status_code == 200
    data = response.json()
    assert data["has_access"] is False
    assert data["subscription"] is None


@pytest.mark.django_db
def test_current_subscription_multiple_overlapping_selects_latest(
    api_client, monthly_plan, yearly_plan
):
    user = User.objects.create_user(username="multi_sub_api")
    now = timezone.now()

    # Subscription 1: expires in 10 days
    Subscription.objects.create(
        user=user,
        plan=monthly_plan,
        status=Subscription.Status.ACTIVE,
        starts_at=now - timedelta(days=5),
        expires_at=now + timedelta(days=10),
    )
    # Subscription 2: expires in 360 days (latest)
    sub_yearly = Subscription.objects.create(
        user=user,
        plan=yearly_plan,
        status=Subscription.Status.ACTIVE,
        starts_at=now - timedelta(days=1),
        expires_at=now + timedelta(days=360),
    )

    api_client.force_authenticate(user=user)
    response = api_client.get("/api/v1/subscriptions/current/")
    assert response.status_code == 200
    data = response.json()
    assert data["has_access"] is True
    assert data["subscription"]["id"] == sub_yearly.id
    assert data["subscription"]["plan"]["code"] == "yearly"
