from __future__ import annotations

import pytest
from django.contrib.auth.models import AnonymousUser

from apps.common.exceptions import APIError
from apps.content import access
from apps.content.models import ContentBlock, Topic


@pytest.mark.django_db
def test_access_matrix_for_published_topics(catalog, make_user, monkeypatch):
    anonymous = AnonymousUser()
    user = make_user(username="reader")
    demo = catalog["add_topic"](title="Demo", slug="demo", position=1)
    free = catalog["add_topic"](
        title="Free",
        slug="free",
        position=2,
        access_level=Topic.AccessLevel.FREE,
    )
    paid = catalog["add_topic"](
        title="Paid",
        slug="paid",
        position=3,
        access_level=Topic.AccessLevel.PAID,
    )

    demo_decision = access.evaluate_topic_access(demo, anonymous)
    assert demo_decision.full_access is True
    assert demo_decision.is_demo_preview is False

    free_anon = access.evaluate_topic_access(free, anonymous)
    assert free_anon.full_access is False
    assert free_anon.is_demo_preview is True

    free_user = access.evaluate_topic_access(free, user)
    assert free_user.full_access is True

    paid_anon = access.evaluate_topic_access(paid, anonymous)
    assert paid_anon.full_access is False
    assert paid_anon.is_demo_preview is True

    paid_user = access.evaluate_topic_access(paid, user)
    assert paid_user.full_access is False
    assert paid_user.is_demo_preview is False

    monkeypatch.setattr(
        access,
        "has_paid_content_entitlement",
        lambda actor: True,
    )
    entitled = access.evaluate_topic_access(paid, user)
    assert entitled.full_access is True


@pytest.mark.django_db
def test_resolve_blocks_demo_returns_everything(catalog):
    topic = catalog["add_topic"](title="Demo", slug="demo", position=1)
    catalog["add_block"](topic, block_type="markdown", position=1, body="# One")
    catalog["add_block"](
        topic,
        block_type="markdown",
        position=2,
        body="# Draft",
        status=ContentBlock.Status.DRAFT,
    )

    decision, blocks = access.resolve_topic_blocks(topic, AnonymousUser())

    assert decision.full_access is True
    assert [block.position for block in blocks] == [1]


@pytest.mark.django_db
def test_resolve_blocks_anonymous_preview_subset(catalog):
    topic = catalog["add_topic"](
        title="Free",
        slug="free",
        position=1,
        access_level=Topic.AccessLevel.FREE,
    )
    catalog["add_block"](topic, block_type="markdown", position=1, body="# Full")
    catalog["add_block"](
        topic,
        block_type="callout",
        position=2,
        body="Preview",
        demo=True,
    )

    decision, blocks = access.resolve_topic_blocks(topic, AnonymousUser())

    assert decision.is_demo_preview is True
    assert [block.position for block in blocks] == [2]


@pytest.mark.django_db
def test_resolve_blocks_anonymous_without_preview_requires_authentication(catalog):
    topic = catalog["add_topic"](
        title="Free",
        slug="free",
        position=1,
        access_level=Topic.AccessLevel.FREE,
    )
    catalog["add_block"](topic, block_type="markdown", position=1, body="# Full")

    with pytest.raises(APIError) as exc:
        access.resolve_topic_blocks(topic, AnonymousUser())

    assert exc.value.default_code == "AUTHENTICATION_REQUIRED"
    assert exc.value.status_code == 401


@pytest.mark.django_db
def test_resolve_blocks_paid_denied_then_allowed_through_policy(
    catalog,
    make_user,
    monkeypatch,
):
    user = make_user(username="reader")
    topic = catalog["add_topic"](
        title="Paid",
        slug="paid",
        position=1,
        access_level=Topic.AccessLevel.PAID,
    )
    catalog["add_block"](topic, block_type="markdown", position=1, body="# Paid")

    with pytest.raises(APIError) as exc:
        access.resolve_topic_blocks(topic, user)
    assert exc.value.default_code == "TOPIC_ENTITLEMENT_REQUIRED"
    assert exc.value.status_code == 403

    monkeypatch.setattr(
        access,
        "has_paid_content_entitlement",
        lambda actor: True,
    )
    decision, blocks = access.resolve_topic_blocks(topic, user)
    assert decision.full_access is True
    assert [block.position for block in blocks] == [1]


@pytest.mark.django_db
def test_resolve_blocks_paid_allowed_with_real_subscription(catalog, make_user):
    from datetime import timedelta
    from decimal import Decimal

    from django.utils import timezone

    from apps.subscriptions.models import Plan, Subscription

    user = make_user(username="real_subscriber")
    plan = Plan.objects.create(
        code="sub-pass",
        title="Pass",
        price_rub=Decimal("990.00"),
        duration_days=30,
        is_active=True,
    )
    now = timezone.now()
    Subscription.objects.create(
        user=user,
        plan=plan,
        status=Subscription.Status.ACTIVE,
        starts_at=now - timedelta(days=1),
        expires_at=now + timedelta(days=29),
    )

    topic = catalog["add_topic"](
        title="Paid Topic Real",
        slug="paid-real",
        position=1,
        access_level=Topic.AccessLevel.PAID,
    )
    catalog["add_block"](
        topic, block_type="markdown", position=1, body="# Paid Content"
    )

    decision, blocks = access.resolve_topic_blocks(topic, user)
    assert decision.full_access is True
    assert len(blocks) == 1
