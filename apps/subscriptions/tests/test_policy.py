from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone

from apps.subscriptions import policy
from apps.subscriptions.models import Plan, Subscription

User = get_user_model()


@pytest.fixture
def plan(db):
    return Plan.objects.create(
        code="standard-monthly",
        title="Standard Monthly",
        description="Standard monthly subscription",
        price_rub=Decimal("990.00"),
        duration_days=30,
        is_active=True,
    )


@pytest.mark.django_db
def test_no_entitlement_source_denies_paid_access():
    user = User.objects.create_user(username="reader")
    assert policy.has_paid_content_entitlement(user) is False


@pytest.mark.django_db
def test_anonymous_and_none_denied_paid_access():
    assert policy.has_paid_content_entitlement(None) is False
    assert policy.has_paid_content_entitlement(AnonymousUser()) is False


@pytest.mark.django_db
def test_policy_is_callable_for_superuser_without_role_bypass():
    user = User(username="root", role=User.Role.ADMIN, is_staff=True, is_superuser=True)
    user.set_unusable_password()
    user.save()

    assert policy.has_paid_content_entitlement(user) is False


@pytest.mark.django_db
def test_active_subscription_grants_entitlement(plan):
    user = User.objects.create_user(username="subscriber")
    now = timezone.now()
    Subscription.objects.create(
        user=user,
        plan=plan,
        status=Subscription.Status.ACTIVE,
        starts_at=now - timedelta(days=1),
        expires_at=now + timedelta(days=29),
    )

    assert policy.has_paid_content_entitlement(user) is True


@pytest.mark.django_db
def test_future_subscription_does_not_grant_entitlement_yet(plan):
    user = User.objects.create_user(username="future_subscriber")
    now = timezone.now()
    Subscription.objects.create(
        user=user,
        plan=plan,
        status=Subscription.Status.ACTIVE,
        starts_at=now + timedelta(days=1),
        expires_at=now + timedelta(days=31),
    )

    assert policy.has_paid_content_entitlement(user) is False


@pytest.mark.django_db
def test_expired_subscription_denies_entitlement(plan):
    user = User.objects.create_user(username="past_subscriber")
    now = timezone.now()
    Subscription.objects.create(
        user=user,
        plan=plan,
        status=Subscription.Status.ACTIVE,
        starts_at=now - timedelta(days=31),
        expires_at=now - timedelta(days=1),
    )

    assert policy.has_paid_content_entitlement(user) is False

    Subscription.objects.filter(user=user).update(status=Subscription.Status.EXPIRED)
    assert policy.has_paid_content_entitlement(user) is False


@pytest.mark.django_db
def test_cancelled_subscription_grants_access_until_period_end(plan):
    user = User.objects.create_user(username="canceller")
    now = timezone.now()
    Subscription.objects.create(
        user=user,
        plan=plan,
        status=Subscription.Status.CANCELLED,
        starts_at=now - timedelta(days=10),
        expires_at=now + timedelta(days=20),
    )

    assert policy.has_paid_content_entitlement(user) is True


@pytest.mark.django_db
def test_cancelled_and_expired_subscription_denies_access(plan):
    user = User.objects.create_user(username="past_canceller")
    now = timezone.now()
    Subscription.objects.create(
        user=user,
        plan=plan,
        status=Subscription.Status.CANCELLED,
        starts_at=now - timedelta(days=35),
        expires_at=now - timedelta(days=5),
    )

    assert policy.has_paid_content_entitlement(user) is False


@pytest.mark.django_db
def test_inactive_user_with_active_subscription_denied(plan):
    user = User.objects.create_user(username="blocked_subscriber", is_active=False)
    now = timezone.now()
    Subscription.objects.create(
        user=user,
        plan=plan,
        status=Subscription.Status.ACTIVE,
        starts_at=now - timedelta(days=1),
        expires_at=now + timedelta(days=29),
    )

    assert policy.has_paid_content_entitlement(user) is False


@pytest.mark.django_db
def test_user_deletion_cascades_subscriptions(plan):
    user = User.objects.create_user(username="temporary_user")
    now = timezone.now()
    Subscription.objects.create(
        user=user,
        plan=plan,
        status=Subscription.Status.ACTIVE,
        starts_at=now - timedelta(days=1),
        expires_at=now + timedelta(days=29),
    )

    user_id = user.id
    assert Subscription.objects.filter(user_id=user_id).count() == 1
    user.delete()
    assert Subscription.objects.filter(user_id=user_id).count() == 0
