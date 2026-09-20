"""API tests for the flashcard review surface under ``/api/v1/`` (feature 003).

The zone contract: ``Z3-flashcards`` owns this file. It exercises the transport
behaviour of T008/T009 — the schedule matrix, the progress transition, the due
filter, the error contract and the concurrent-review invariant.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.db import connections
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.throttling import ScopedRateThrottle

from apps.content.models import Flashcard, Section, Subject, Topic
from apps.learning.flashcards import services
from apps.learning.flashcards.selectors import due_flashcard_reviews
from apps.learning.models import FlashcardReview, UserTopicProgress

User = get_user_model()

DUE_URL = "/api/v1/flashcards/review-due/"


def _topic_flashcards_url(topic_id: int) -> str:
    return f"/api/v1/topics/{topic_id}/flashcards/"


def _detail_url(pk: int) -> str:
    return f"/api/v1/flashcards/{pk}/"


def _review_url(pk: int) -> str:
    return f"/api/v1/flashcards/{pk}/review/"


def _review(client, card, action: str):
    return client.post(_review_url(card.pk), {"action": action}, format="json")


# ---------------------------------------------------------------------------
# List / detail reads.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_topic_list_and_detail_report_null_review_before_the_first_review(
    api_client, make_user, authenticate, demo_topic, make_flashcard
):
    user = make_user()
    client = authenticate(api_client, user)
    first = make_flashcard(demo_topic, question="First?", position=2)
    second = make_flashcard(demo_topic, question="Second?", position=1)

    listing = client.get(_topic_flashcards_url(demo_topic.pk))

    assert listing.status_code == 200
    body = listing.json()
    assert body["count"] == 2
    assert [item["id"] for item in body["results"]] == [second.pk, first.pk]
    assert body["results"][0]["topic"] == demo_topic.pk
    assert body["results"][0]["question"] == "Second?"
    assert all(item["review"] is None for item in body["results"])

    detail = client.get(_detail_url(first.pk))

    assert detail.status_code == 200
    assert detail.json()["id"] == first.pk
    assert detail.json()["review"] is None


@pytest.mark.django_db
def test_detail_reports_the_current_review_state_after_a_review(
    api_client, make_user, authenticate, demo_topic, make_flashcard
):
    user = make_user()
    client = authenticate(api_client, user)
    card = make_flashcard(demo_topic)

    assert _review(client, card, "know").status_code == 201

    detail = client.get(_detail_url(card.pk))

    assert detail.status_code == 200
    assert detail.json()["review"]["interval_days"] == 1
    assert detail.json()["review"]["repetitions"] == 1


# ---------------------------------------------------------------------------
# Review schedule through the API.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("action", "expected_repetitions"),
    [("know", 1), ("repeat", 0)],
)
@pytest.mark.django_db
def test_first_review_creates_the_row_on_the_first_interval(
    api_client,
    make_user,
    authenticate,
    demo_topic,
    make_flashcard,
    settings,
    action,
    expected_repetitions,
):
    user = make_user()
    client = authenticate(api_client, user)
    card = make_flashcard(demo_topic)

    response = _review(client, card, action)

    assert response.status_code == 201
    review = response.json()["review"]
    assert review["interval_days"] == settings.LEARNING_FLASHCARD_INTERVALS[0]
    assert review["repetitions"] == expected_repetitions
    assert review["last_reviewed_at"] is not None
    assert review["next_review_at"] is not None
    assert FlashcardReview.objects.filter(user=user, flashcard=card).count() == 1


@pytest.mark.django_db
def test_know_advances_one_interval_repeat_resets_and_one_row_is_kept(
    api_client, make_user, authenticate, demo_topic, make_flashcard
):
    user = make_user()
    client = authenticate(api_client, user)
    card = make_flashcard(demo_topic)

    expected = (("know", 1, 1), ("know", 3, 2), ("know", 7, 3), ("repeat", 1, 0))

    for index, (action, interval_days, repetitions) in enumerate(expected):
        response = _review(client, card, action)
        assert response.status_code == 201 if index == 0 else 200
        assert response.json()["review"]["interval_days"] == interval_days
        assert response.json()["review"]["repetitions"] == repetitions

    assert FlashcardReview.objects.filter(user=user, flashcard=card).count() == 1


@pytest.mark.django_db
def test_know_stays_on_the_last_interval(
    api_client, make_user, authenticate, demo_topic, make_flashcard
):
    user = make_user()
    client = authenticate(api_client, user)
    card = make_flashcard(demo_topic)
    last = 30
    FlashcardReview.objects.create(
        user=user,
        flashcard=card,
        interval_days=last,
        repetitions=5,
        last_reviewed_at=timezone.now() - timedelta(days=last),
        next_review_at=timezone.now(),
    )

    response = _review(client, card, "know")

    assert response.status_code == 200
    assert response.json()["review"]["interval_days"] == last
    assert response.json()["review"]["repetitions"] == 6


# ---------------------------------------------------------------------------
# Progress transition.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_review_creates_the_topic_progress_row_as_learning(
    api_client, make_user, authenticate, demo_topic, make_flashcard
):
    user = make_user()
    client = authenticate(api_client, user)
    card = make_flashcard(demo_topic)

    assert not UserTopicProgress.objects.filter(user=user, topic=demo_topic).exists()

    assert _review(client, card, "know").status_code == 201

    progress = UserTopicProgress.objects.get(user=user, topic=demo_topic)
    assert progress.status == UserTopicProgress.Status.LEARNING
    assert progress.started_at is not None
    assert progress.last_opened_at is None


@pytest.mark.django_db
def test_review_does_not_regress_a_learned_topic_progress(
    api_client, make_user, authenticate, demo_topic, make_flashcard
):
    user = make_user()
    client = authenticate(api_client, user)
    card = make_flashcard(demo_topic)
    now = timezone.now()
    UserTopicProgress.objects.create(
        user=user,
        topic=demo_topic,
        status=UserTopicProgress.Status.LEARNED,
        started_at=now,
        completed_at=now,
    )

    assert _review(client, card, "repeat").status_code == 201

    progress = UserTopicProgress.objects.get(user=user, topic=demo_topic)
    assert progress.status == UserTopicProgress.Status.LEARNED
    assert progress.completed_at == now


# ---------------------------------------------------------------------------
# Due selector.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_due_list_keeps_only_past_published_accessible_reviews(
    api_client,
    make_user,
    authenticate,
    demo_topic,
    free_topic,
    paid_topic,
    draft_topic,
    make_flashcard,
):
    user = make_user()
    client = authenticate(api_client, user)
    now = timezone.now()
    early = now - timedelta(days=2)
    late = now - timedelta(days=1)
    future = now + timedelta(days=1)

    demo_card = make_flashcard(demo_topic)
    free_card = make_flashcard(free_topic)
    future_card = make_flashcard(demo_topic)
    never_card = make_flashcard(demo_topic)
    paid_card = make_flashcard(paid_topic)
    draft_card = make_flashcard(draft_topic)
    for card, next_at in (
        (demo_card, early),
        (free_card, late),
        (future_card, future),
        (paid_card, early),
        (draft_card, early),
    ):
        FlashcardReview.objects.create(
            user=user,
            flashcard=card,
            interval_days=1,
            repetitions=1,
            last_reviewed_at=now - timedelta(days=3),
            next_review_at=next_at,
        )

    response = client.get(DUE_URL)

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body["results"]] == [demo_card.pk, free_card.pk]
    assert all(item["review"] is not None for item in body["results"])
    assert never_card.pk not in [item["id"] for item in body["results"]]


@pytest.mark.parametrize("paid_count", [1, 5])
@pytest.mark.django_db
def test_due_selector_keeps_paid_entitlement_queries_bounded(
    make_user, make_topic, make_flashcard, django_assert_num_queries, paid_count
):
    user = make_user()
    now = timezone.now()

    for index in range(paid_count):
        topic = make_topic(
            title=f"Paid topic {index}",
            access_level=Topic.AccessLevel.PAID,
        )
        card = make_flashcard(topic)
        FlashcardReview.objects.create(
            user=user,
            flashcard=card,
            interval_days=1,
            repetitions=1,
            last_reviewed_at=now - timedelta(days=1),
            next_review_at=now,
        )

    with django_assert_num_queries(2):
        due = due_flashcard_reviews(user, now=now)

    assert due == []


# ---------------------------------------------------------------------------
# Access and error contract.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_review_rejects_an_invalid_action_with_422(
    api_client, make_user, authenticate, demo_topic, make_flashcard
):
    client = authenticate(api_client, make_user())
    card = make_flashcard(demo_topic)

    response = _review(client, card, "maybe")

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert "action" in body["fields"]
    assert FlashcardReview.objects.count() == 0


@pytest.mark.django_db
def test_review_rejects_an_unknown_field_with_422(
    api_client, make_user, authenticate, demo_topic, make_flashcard
):
    client = authenticate(api_client, make_user())
    card = make_flashcard(demo_topic)

    response = client.post(
        _review_url(card.pk),
        {"action": "know", "surprise": 1},
        format="json",
    )

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["fields"] == {"surprise": ["Unknown field."]}


@pytest.mark.django_db
def test_review_and_reads_require_authentication(
    api_client, demo_topic, make_flashcard
):
    card = make_flashcard(demo_topic)

    anonymous = (
        api_client.get(_topic_flashcards_url(demo_topic.pk)),
        api_client.get(DUE_URL),
        api_client.get(_detail_url(card.pk)),
        api_client.post(_review_url(card.pk), {"action": "know"}, format="json"),
    )

    for response in anonymous:
        assert response.status_code == 401
        assert response.json()["code"] == "AUTHENTICATION_REQUIRED"
    assert FlashcardReview.objects.count() == 0


@pytest.mark.django_db
def test_flashcard_of_an_unpublished_topic_is_404(
    api_client, make_user, authenticate, draft_topic, make_flashcard
):
    client = authenticate(api_client, make_user())
    card = make_flashcard(draft_topic)

    assert client.get(_detail_url(card.pk)).status_code == 404
    assert client.get(_detail_url(10_000_000)).status_code == 404
    assert _review(client, card, "know").status_code == 404


@pytest.mark.django_db
def test_flashcard_of_a_paid_topic_without_entitlement_is_403(
    api_client, make_user, authenticate, paid_topic, make_flashcard
):
    client = authenticate(api_client, make_user())
    card = make_flashcard(paid_topic)

    responses = (
        client.get(_detail_url(card.pk)),
        _review(client, card, "know"),
    )

    for response in responses:
        assert response.status_code == 403
        assert response.json()["code"] == "TOPIC_ENTITLEMENT_REQUIRED"


@pytest.mark.django_db
def test_review_state_is_isolated_per_user(
    api_client, authenticate, make_user, demo_topic, make_flashcard
):
    """Another user's review state is invisible and stays untouched by their action."""

    owner = make_user(username="owner")
    other = make_user(username="other")
    card = make_flashcard(demo_topic)
    authenticate(api_client, owner)
    assert _review(api_client, card, "know").status_code == 201

    authenticate(api_client, other)

    listing = api_client.get(_topic_flashcards_url(demo_topic.pk)).json()
    assert [item["review"] for item in listing["results"]] == [None]
    assert api_client.get(_detail_url(card.pk)).json()["review"] is None
    assert api_client.get(DUE_URL).json()["count"] == 0

    assert _review(api_client, card, "repeat").status_code == 201

    owned = FlashcardReview.objects.get(user=owner, flashcard=card)
    assert (owned.interval_days, owned.repetitions) == (1, 1)
    fresh = FlashcardReview.objects.get(user=other, flashcard=card)
    assert (fresh.interval_days, fresh.repetitions) == (1, 0)
    assert FlashcardReview.objects.filter(flashcard=card).count() == 2


@pytest.mark.django_db
def test_review_actions_are_throttled_by_the_review_scope(
    api_client, authenticate, make_user, demo_topic, make_flashcard, monkeypatch
):
    """The review write uses ``learning_review`` while reads keep ``learning_read``."""

    monkeypatch.setattr(
        ScopedRateThrottle,
        "THROTTLE_RATES",
        {"learning_review": "2/min", "learning_read": "120/min"},
    )
    user = make_user()
    authenticate(api_client, user)
    card = make_flashcard(demo_topic)

    assert _review(api_client, card, "know").status_code == 201
    assert _review(api_client, card, "know").status_code == 200

    throttled = _review(api_client, card, "know")

    assert throttled.status_code == 429
    assert throttled.json()["code"] == "THROTTLED"
    assert api_client.get(_detail_url(card.pk)).status_code == 200
    stored = FlashcardReview.objects.get(user=user, flashcard=card)
    assert (stored.interval_days, stored.repetitions) == (3, 2)


# ---------------------------------------------------------------------------
# Concurrency.
# ---------------------------------------------------------------------------


def _racing_user(username: str = "racer"):
    user = User(username=username, role=User.Role.USER)
    user.set_unusable_password()
    user.save()
    return user


def _racing_flashcard(slug: str = "cards") -> Flashcard:
    """A published demo topic holding one flashcard, built without fixtures."""

    subject = Subject.objects.create(
        title="Pharmacology",
        slug="pharmacology",
        position=1,
    )
    section = Section.objects.create(
        subject=subject,
        title="Antibiotics",
        slug="antibiotics",
        position=1,
    )
    topic = Topic.objects.create(
        section=section,
        title="Cards",
        slug=slug,
        position=1,
        status=Topic.Status.PUBLISHED,
        access_level=Topic.AccessLevel.DEMO,
    )
    return Flashcard.objects.create(
        topic=topic,
        question="Which ring is strained?",
        answer="The beta-lactam ring",
        position=1,
    )


class ConcurrentFlashcardReviewTests(TransactionTestCase):
    """Two real transactions racing on the review row of one card."""

    def test_concurrent_first_reviews_keep_one_row_and_both_succeed(self):
        user = _racing_user()
        flashcard = _racing_flashcard()

        barrier = threading.Barrier(2)
        real_find = services._find_review

        def synchronized_find(user_, flashcard_):
            # Both transactions observe "no row" before either inserts, so the
            # unique constraint (not scheduling luck) decides the winner.
            review = real_find(user_, flashcard_)
            if review is None:
                barrier.wait(timeout=10)
            return review

        def review(_index: int):
            try:
                row, created = services.review_flashcard(
                    user,
                    flashcard,
                    action=services.ACTION_KNOW,
                )
                return ("created" if created else "updated", row.pk)
            finally:
                connections.close_all()

        with mock.patch.object(services, "_find_review", synchronized_find):
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(review, range(2)))

        self.assertEqual(
            FlashcardReview.objects.filter(user=user, flashcard=flashcard).count(),
            1,
        )
        self.assertEqual(
            sorted(outcome for outcome, _ in results),
            ["created", "updated"],
        )
        self.assertEqual(len({pk for _, pk in results}), 1)

    def test_concurrent_know_actions_advance_the_schedule_twice(self):
        """Both ``know`` actions land on the existing row: 1 → 3 → 7.

        The two transactions are released together and both must read the row
        before either writes it, so a lost update is possible without the row
        lock. The locked reader is held in the database until the first
        transaction commits, which is exactly what the barrier timeout observes:
        only the second transaction can read the committed ``3`` and advance it.
        """

        user = _racing_user()
        flashcard = _racing_flashcard()
        now = timezone.now()
        FlashcardReview.objects.create(
            user=user,
            flashcard=flashcard,
            interval_days=1,
            repetitions=1,
            last_reviewed_at=now,
            next_review_at=now + timedelta(days=1),
        )

        entered = threading.Barrier(2)
        read = threading.Barrier(2)
        real_find = services._find_review

        def synchronized_find(user_, flashcard_):
            review = real_find(user_, flashcard_)
            try:
                read.wait(timeout=2)
            except threading.BrokenBarrierError:
                # The other transaction is blocked on the row lock, so it cannot
                # reach the barrier before this transaction commits.
                pass
            return review

        def review(_index: int):
            try:
                entered.wait(timeout=10)
                row, _created = services.review_flashcard(
                    user,
                    flashcard,
                    action=services.ACTION_KNOW,
                )
                return row.pk
            finally:
                connections.close_all()

        with mock.patch.object(services, "_find_review", synchronized_find):
            with ThreadPoolExecutor(max_workers=2) as executor:
                pks = list(executor.map(review, range(2)))

        stored = FlashcardReview.objects.get(user=user, flashcard=flashcard)
        self.assertEqual(stored.interval_days, 7)
        self.assertEqual(stored.repetitions, 3)
        self.assertEqual(len(set(pks)), 1)
