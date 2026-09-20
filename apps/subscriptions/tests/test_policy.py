from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone

from apps.subscriptions import policy
from apps.subscriptions.models import Plan, Subscription
from apps.subscriptions.selectors import get_active_subscription

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
def test_expired_subscription_by_time_denies_entitlement(plan):
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
def test_multiple_overlapping_subscriptions_grant_entitlement_and_select_latest(
    plan,
):
    user = User.objects.create_user(username="multi_sub")
    now = timezone.now()

    # Sub 1: Active, expires in 10 days
    Subscription.objects.create(
        user=user,
        plan=plan,
        status=Subscription.Status.ACTIVE,
        starts_at=now - timedelta(days=5),
        expires_at=now + timedelta(days=10),
    )
    # Sub 2: Cancelled, expires in 25 days
    Subscription.objects.create(
        user=user,
        plan=plan,
        status=Subscription.Status.CANCELLED,
        starts_at=now - timedelta(days=2),
        expires_at=now + timedelta(days=25),
    )
    # Sub 3: Active, expires in 40 days (the latest)
    sub3 = Subscription.objects.create(
        user=user,
        plan=plan,
        status=Subscription.Status.ACTIVE,
        starts_at=now - timedelta(days=1),
        expires_at=now + timedelta(days=40),
    )

    # Entitlement is True
    assert policy.has_paid_content_entitlement(user) is True

    # get_active_subscription selects sub3 (latest expires_at)
    active = get_active_subscription(user)
    assert active is not None
    assert active.pk == sub3.pk

    # After 15 days: sub1 expired, sub2 and sub3 still active -> select sub3
    at_15d = now + timedelta(days=15)
    assert (
        get_active_subscription(user, at_time=at_15d).pk  # type: ignore[union-attr]
        == sub3.pk
    )

    # After 30 days: sub1 and sub2 expired, sub3 still active
    at_30d = now + timedelta(days=30)
    assert (
        get_active_subscription(user, at_time=at_30d).pk  # type: ignore[union-attr]
        == sub3.pk
    )

    # After 45 days: all expired
    at_45d = now + timedelta(days=45)
    assert get_active_subscription(user, at_time=at_45d) is None


@pytest.mark.django_db
def test_overlapping_subscriptions_with_same_expiry_selects_newest_id(plan):
    user = User.objects.create_user(username="same_exp_user")
    now = timezone.now()
    exp = now + timedelta(days=30)

    sub_older = Subscription.objects.create(
        user=user,
        plan=plan,
        status=Subscription.Status.ACTIVE,
        starts_at=now - timedelta(days=2),
        expires_at=exp,
    )
    sub_newer = Subscription.objects.create(
        user=user,
        plan=plan,
        status=Subscription.Status.ACTIVE,
        starts_at=now - timedelta(days=1),
        expires_at=exp,
    )

    active = get_active_subscription(user)
    assert active is not None
    assert sub_newer.pk > sub_older.pk
    assert active.pk == sub_newer.pk


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
