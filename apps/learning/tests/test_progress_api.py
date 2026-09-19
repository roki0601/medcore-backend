"""API tests for the theory-progress surface under ``/api/v1/topics/``."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.db import connections
from django.test import TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.throttling import ScopedRateThrottle

from apps.content.models import ContentBlock, Section, Subject, Topic
from apps.learning import services
from apps.learning.models import UserTopicBlockProgress, UserTopicProgress
from apps.learning.progress import services as progress_services

User = get_user_model()


def _progress_url(topic) -> str:
    return f"/api/v1/topics/{topic.pk}/progress/"


def _block_url(topic, block) -> str:
    return f"/api/v1/topics/{topic.pk}/blocks/{block.pk}/complete/"


def _make_blocks(make_block, topic, count: int) -> list[ContentBlock]:
    return [make_block(topic, position=index + 1) for index in range(count)]


@pytest.mark.django_db
def test_progress_routes_use_the_contract_names(demo_topic, published_block):
    assert reverse("learning-topic-progress", args=[demo_topic.pk]) == _progress_url(
        demo_topic
    )
    assert reverse(
        "learning-topic-block-complete",
        args=[demo_topic.pk, published_block.pk],
    ) == _block_url(demo_topic, published_block)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("total_blocks", "completed_blocks", "expected_percent"),
    [
        (0, 0, 0),  # an empty topic reports 0, not an error
        (3, 0, 0),
        (2, 1, 50),
        (3, 1, 33),  # 33.33 rounds down
        (3, 2, 67),  # 66.67 rounds up
        (8, 1, 13),  # 12.5 rounds half up
        (3, 3, 100),
    ],
)
def test_progress_percentage_boundaries(
    api_client,
    authenticate,
    make_user,
    demo_topic,
    make_block,
    total_blocks,
    completed_blocks,
    expected_percent,
):
    user = make_user()
    authenticate(api_client, user)
    blocks = _make_blocks(make_block, demo_topic, total_blocks)
    for block in blocks[:completed_blocks]:
        assert api_client.post(_block_url(demo_topic, block)).status_code == 201

    body = api_client.get(_progress_url(demo_topic)).json()

    assert body["theory_percent"] == expected_percent
    assert body["completed_blocks"] == completed_blocks
    assert body["total_blocks"] == total_blocks


@pytest.mark.django_db
def test_get_progress_creates_no_rows(
    api_client, authenticate, make_user, demo_topic, make_block
):
    user = make_user()
    authenticate(api_client, user)
    make_block(demo_topic)

    response = api_client.get(_progress_url(demo_topic))

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "not_started"
    assert body["total_blocks"] == 1
    assert body["last_opened_at"] is None
    assert body["started_at"] is None
    assert body["completed_at"] is None
    assert UserTopicProgress.objects.count() == 0
    assert UserTopicBlockProgress.objects.count() == 0


@pytest.mark.django_db
def test_block_completion_is_idempotent_and_starts_the_topic(
    api_client, authenticate, make_user, demo_topic, make_block
):
    user = make_user()
    authenticate(api_client, user)
    block = make_block(demo_topic)

    first = api_client.post(_block_url(demo_topic, block))

    assert first.status_code == 201
    body = first.json()
    assert body["completed_blocks"] == 1
    assert body["theory_percent"] == 100
    assert body["status"] == "learning"
    assert body["started_at"] is not None

    repeat = api_client.post(_block_url(demo_topic, block))

    assert repeat.status_code == 200
    assert repeat.json()["completed_blocks"] == 1
    assert repeat.json()["status"] == "learning"
    assert (
        UserTopicBlockProgress.objects.filter(
            user=user, block=block, is_complete=True
        ).count()
        == 1
    )
    assert UserTopicProgress.objects.filter(user=user, topic=demo_topic).count() == 1


@pytest.mark.django_db
def test_draft_blocks_are_excluded_and_cannot_be_completed(
    api_client, authenticate, make_user, demo_topic, make_block
):
    user = make_user()
    authenticate(api_client, user)
    published = make_block(demo_topic, position=1)
    draft = make_block(demo_topic, position=2, status=ContentBlock.Status.DRAFT)

    body = api_client.get(_progress_url(demo_topic)).json()

    assert body["total_blocks"] == 1
    assert api_client.post(_block_url(demo_topic, published)).status_code == 201

    rejected = api_client.post(_block_url(demo_topic, draft))

    assert rejected.status_code == 404
    assert rejected.json()["code"] == "RESOURCE_NOT_FOUND"
    assert UserTopicBlockProgress.objects.filter(block=draft).count() == 0


@pytest.mark.django_db
def test_block_of_another_topic_is_not_found(
    api_client, authenticate, make_user, demo_topic, make_topic, make_block
):
    user = make_user()
    authenticate(api_client, user)
    other = make_topic(title="Other topic")
    foreign_block = make_block(other)

    response = api_client.post(_block_url(demo_topic, foreign_block))

    assert response.status_code == 404
    assert response.json()["code"] == "RESOURCE_NOT_FOUND"
    assert UserTopicBlockProgress.objects.count() == 0


@pytest.mark.django_db
def test_unpublished_topic_is_not_found(
    api_client, authenticate, make_user, draft_topic
):
    user = make_user()
    authenticate(api_client, user)

    read = api_client.get(_progress_url(draft_topic))
    write = api_client.patch(
        _progress_url(draft_topic), {"opened": True}, format="json"
    )

    assert read.status_code == 404
    assert read.json()["code"] == "RESOURCE_NOT_FOUND"
    assert write.status_code == 404
    assert write.json()["code"] == "RESOURCE_NOT_FOUND"
    assert UserTopicProgress.objects.count() == 0


@pytest.mark.django_db
def test_paid_topic_requires_entitlement(
    api_client, authenticate, make_user, paid_topic, make_block, monkeypatch
):
    user = make_user()
    authenticate(api_client, user)
    block = make_block(paid_topic)

    denied = api_client.get(_progress_url(paid_topic))
    denied_block = api_client.post(_block_url(paid_topic, block))

    assert denied.status_code == 403
    assert denied.json()["code"] == "TOPIC_ENTITLEMENT_REQUIRED"
    assert denied_block.status_code == 403
    assert denied_block.json()["code"] == "TOPIC_ENTITLEMENT_REQUIRED"

    monkeypatch.setattr(
        "apps.content.access.has_paid_content_entitlement",
        lambda actor: True,
    )
    allowed = api_client.get(_progress_url(paid_topic))

    assert allowed.status_code == 200


@pytest.mark.django_db
def test_progress_endpoints_require_authentication(
    api_client, demo_topic, published_block
):
    requests = (
        lambda: api_client.get(_progress_url(demo_topic)),
        lambda: api_client.patch(
            _progress_url(demo_topic), {"opened": True}, format="json"
        ),
        lambda: api_client.post(_block_url(demo_topic, published_block)),
    )

    for request in requests:
        response = request()
        assert response.status_code == 401
        assert response.json()["code"] == "AUTHENTICATION_REQUIRED"

    assert UserTopicProgress.objects.count() == 0
    assert UserTopicBlockProgress.objects.count() == 0


@pytest.mark.django_db
def test_progress_patch_rejects_unknown_and_empty_payloads(
    api_client, authenticate, make_user, demo_topic
):
    user = make_user()
    authenticate(api_client, user)

    unknown = api_client.patch(
        _progress_url(demo_topic),
        {"opened": True, "surprise": 1},
        format="json",
    )
    empty = api_client.patch(_progress_url(demo_topic), {}, format="json")
    invalid_status = api_client.patch(
        _progress_url(demo_topic), {"status": "learning"}, format="json"
    )

    assert unknown.status_code == 422
    assert unknown.json()["code"] == "VALIDATION_ERROR"
    assert unknown.json()["fields"] == {"surprise": ["Unknown field."]}
    assert empty.status_code == 422
    assert empty.json()["code"] == "VALIDATION_ERROR"
    assert invalid_status.status_code == 422
    assert "status" in invalid_status.json()["fields"]
    assert UserTopicProgress.objects.count() == 0


@pytest.mark.django_db
def test_progress_open_and_learned_transitions_never_regress(
    api_client, authenticate, make_user, demo_topic, make_block
):
    user = make_user()
    authenticate(api_client, user)
    block = make_block(demo_topic)

    opened = api_client.patch(
        _progress_url(demo_topic), {"opened": True}, format="json"
    )

    assert opened.status_code == 200
    opened_body = opened.json()
    assert opened_body["status"] == "learning"
    assert opened_body["last_opened_at"] is not None
    assert opened_body["started_at"] is not None
    assert opened_body["completed_at"] is None

    learned = api_client.patch(
        _progress_url(demo_topic), {"status": "learned"}, format="json"
    )

    assert learned.status_code == 200
    learned_body = learned.json()
    assert learned_body["status"] == "learned"
    completed_at = learned_body["completed_at"]
    assert completed_at is not None

    completed_block = api_client.post(_block_url(demo_topic, block))
    reopened = api_client.patch(
        _progress_url(demo_topic), {"opened": True}, format="json"
    )

    assert completed_block.json()["status"] == "learned"
    assert reopened.json()["status"] == "learned"
    assert reopened.json()["completed_at"] == completed_at
    assert reopened.json()["last_opened_at"] is not None


@pytest.mark.django_db
def test_learned_is_allowed_without_theory_blocks(
    api_client, authenticate, make_user, demo_topic
):
    user = make_user()
    authenticate(api_client, user)

    response = api_client.patch(
        _progress_url(demo_topic), {"status": "learned"}, format="json"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "learned"
    assert body["completed_at"] is not None
    assert body["theory_percent"] == 0
    assert body["total_blocks"] == 0


@pytest.mark.django_db
def test_reparented_block_stops_counting_for_the_old_topic(
    api_client, authenticate, make_user, demo_topic, make_topic, make_block
):
    user = make_user()
    authenticate(api_client, user)
    block = make_block(demo_topic)
    assert api_client.post(_block_url(demo_topic, block)).status_code == 201

    other = make_topic(title="Other topic")
    ContentBlock.objects.filter(pk=block.pk).update(topic=other)

    old_topic = api_client.get(_progress_url(demo_topic)).json()
    new_topic = api_client.get(_progress_url(other)).json()

    # The completion row is derived from the block side, so the count follows
    # the block to its new topic and the old topic loses it entirely.
    assert (old_topic["completed_blocks"], old_topic["total_blocks"]) == (0, 0)
    assert old_topic["theory_percent"] == 0
    assert (new_topic["completed_blocks"], new_topic["total_blocks"]) == (1, 1)
    assert new_topic["theory_percent"] == 100


@pytest.mark.django_db
def test_progress_is_isolated_per_user(
    api_client, authenticate, make_user, demo_topic, make_block
):
    """Another user's completion and learned transition leave the owner untouched."""

    owner = make_user(username="owner")
    other = make_user(username="other")
    block = make_block(demo_topic)
    authenticate(api_client, owner)
    assert api_client.post(_block_url(demo_topic, block)).status_code == 201

    authenticate(api_client, other)

    fresh = api_client.get(_progress_url(demo_topic)).json()
    assert fresh["status"] == "not_started"
    assert (fresh["completed_blocks"], fresh["theory_percent"]) == (0, 0)
    assert fresh["started_at"] is None

    learned = api_client.patch(
        _progress_url(demo_topic), {"status": "learned"}, format="json"
    )

    assert learned.status_code == 200
    assert learned.json()["status"] == "learned"
    assert learned.json()["completed_blocks"] == 0

    authenticate(api_client, owner)
    own = api_client.get(_progress_url(demo_topic)).json()

    assert own["status"] == "learning"
    assert own["completed_blocks"] == 1
    assert own["completed_at"] is None
    assert UserTopicProgress.objects.filter(topic=demo_topic).count() == 2
    assert UserTopicBlockProgress.objects.filter(block=block).count() == 1


@pytest.mark.django_db
def test_block_completion_rejects_a_non_empty_body(
    api_client, authenticate, make_user, demo_topic, make_block
):
    """The empty-body route rejects any provided key and accepts both empty forms."""

    authenticate(api_client, make_user())
    first = make_block(demo_topic, position=1)
    second = make_block(demo_topic, position=2)

    unknown = api_client.post(
        _block_url(demo_topic, first),
        {"surprise": 1},
        format="json",
    )

    assert unknown.status_code == 422
    assert unknown.json()["code"] == "VALIDATION_ERROR"
    assert unknown.json()["fields"] == {"surprise": ["Unknown field."]}
    assert UserTopicBlockProgress.objects.count() == 0

    empty_json = api_client.post(_block_url(demo_topic, first), {}, format="json")
    bodyless = api_client.post(_block_url(demo_topic, second))

    assert empty_json.status_code == 201
    assert bodyless.status_code == 201
    assert UserTopicBlockProgress.objects.count() == 2


# ---------------------------------------------------------------------------
# Concurrency (real transactions).
# ---------------------------------------------------------------------------


def _racing_user(username: str = "racer"):
    user = User(username=username, role=User.Role.USER)
    user.set_unusable_password()
    user.save()
    return user


def _racing_topic(slug: str = "racing-topic") -> Topic:
    subject = Subject.objects.create(
        title="Pharmacology",
        slug=f"{slug}-subject",
        position=1,
    )
    section = Section.objects.create(
        subject=subject,
        title="Antibiotics",
        slug=f"{slug}-section",
        position=1,
    )
    return Topic.objects.create(
        section=section,
        title="Beta-lactams",
        slug=slug,
        position=1,
        status=Topic.Status.PUBLISHED,
        access_level=Topic.AccessLevel.DEMO,
    )


class ConcurrentProgressTransitionTests(TransactionTestCase):
    """``{"opened": true}`` racing the manual ``learned`` transition."""

    def test_concurrent_open_cannot_regress_a_learned_topic(self):
        """The stale opening write is a no-op, so ``learned`` and ``completed_at`` hold.

        The opening reads the row before the learned transition writes it and is
        released only after that transaction committed, so its write is a genuine
        stale write; the conditional update must not match the learned row.
        """

        user = _racing_user()
        topic = _racing_topic()
        now = timezone.now()
        UserTopicProgress.objects.create(
            user=user,
            topic=topic,
            status=UserTopicProgress.Status.LEARNING,
            started_at=now,
        )

        opened_read = threading.Event()
        learned_committed = threading.Event()
        role = threading.local()
        real_get_or_create = services._get_or_create

        def synchronized_get_or_create(user_, topic_):
            progress = real_get_or_create(user_, topic_)
            if getattr(role, "opening", False):
                opened_read.set()
                assert learned_committed.wait(timeout=10)
            return progress

        def open_topic():
            role.opening = True
            try:
                return progress_services.open_topic(user, topic)
            finally:
                connections.close_all()

        def mark_learned():
            try:
                assert opened_read.wait(timeout=10)
                return progress_services.mark_topic_learned(user, topic)
            finally:
                connections.close_all()

        with mock.patch.object(services, "_get_or_create", synchronized_get_or_create):
            with ThreadPoolExecutor(max_workers=2) as executor:
                opening = executor.submit(open_topic)
                learned = executor.submit(mark_learned)
                learned_row = learned.result(timeout=30)
                learned_committed.set()
                opening.result(timeout=30)

        stored = UserTopicProgress.objects.get(user=user, topic=topic)
        self.assertEqual(stored.status, UserTopicProgress.Status.LEARNED)
        self.assertIsNotNone(learned_row.completed_at)
        self.assertEqual(stored.completed_at, learned_row.completed_at)
        self.assertIsNotNone(stored.last_opened_at)


@pytest.mark.django_db
def test_progress_methods_use_distinct_throttle_scopes(
    api_client, authenticate, make_user, demo_topic, monkeypatch
):
    user = make_user()
    authenticate(api_client, user)
    monkeypatch.setattr(
        ScopedRateThrottle,
        "THROTTLE_RATES",
        {"learning_read": "100/min", "learning_progress": "2/min"},
    )

    body = {"opened": True}
    assert (
        api_client.patch(_progress_url(demo_topic), body, format="json").status_code
        == 200
    )
    assert (
        api_client.patch(_progress_url(demo_topic), body, format="json").status_code
        == 200
    )

    throttled = api_client.patch(_progress_url(demo_topic), body, format="json")

    assert throttled.status_code == 429
    assert throttled.json()["code"] == "THROTTLED"
    assert api_client.get(_progress_url(demo_topic)).status_code == 200
