from __future__ import annotations

import threading
from unittest import mock
from uuid import uuid4

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.db import connections
from django.test import TransactionTestCase
from rest_framework.test import APIClient
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.media import services
from apps.media import views as media_views
from apps.media.models import MediaFile

User = get_user_model()

MEDIA_URL = "/api/v1/media/"
BLOCKS_URL = "/api/v1/content/blocks/"
PUBLISHED = "published"


def _content_model(name: str):
    """Resolve one content model through Django's application registry.

    The media app never imports the content app; these concurrency tests still
    need a real draft image block and a real publish, so the models are resolved
    at runtime and the publish goes through the content HTTP surface.
    """

    return django_apps.get_model("content", name)


def _create_draft_image_block(media: MediaFile):
    """Create a draft image block referencing ``media`` through the registry."""

    suffix = uuid4().hex[:8]
    Subject = _content_model("Subject")
    Section = _content_model("Section")
    Topic = _content_model("Topic")
    ContentBlock = _content_model("ContentBlock")
    block_type = _content_model("ContentBlockType").objects.get(key="image")
    subject = Subject.objects.create(
        title=f"Subject {suffix}",
        slug=f"subject-{suffix}",
        position=1,
    )
    section = Section.objects.create(
        subject=subject,
        title=f"Section {suffix}",
        slug=f"section-{suffix}",
        position=1,
    )
    topic = Topic.objects.create(
        section=section,
        title=f"Topic {suffix}",
        slug=f"topic-{suffix}",
        position=1,
        status=PUBLISHED,
        access_level="demo",
    )
    return ContentBlock.objects.create(
        topic=topic,
        block_type=block_type,
        position=1,
        status="draft",
        media=media,
    )


def _author_client(username: str) -> APIClient:
    """An API client authenticated with an editor JWT."""

    user = User(username=username, role=User.Role.EDITOR, is_staff=True)
    user.set_unusable_password()
    user.save()
    access = RefreshToken.for_user(user).access_token
    access["auth_version"] = user.auth_version
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


def _outcome(response) -> tuple[int, str | None]:
    """The status and the error code of one response; 204 carries no body."""

    body = response.json() if response.content else {}
    return response.status_code, body.get("code")


class PublishVersusDeleteTests(TransactionTestCase):
    """A concurrent publish and media delete must serialize on the media row.

    The delete transaction locks the ``MediaFile`` row and asks the content-owned
    guard inside that transaction, while the publish runs as a real concurrent
    request. The only admissible outcomes are the documented ones (409
    ``CONTENT_CONFLICT`` for the delete, or 409 ``INVALID_CONTENT_STATE`` /
    ``CONTENT_CONFLICT`` for the publish), and a published block must never be
    left without its media.
    """

    def _media_with_draft_block(self):
        ContentBlock = _content_model("ContentBlock")
        media = MediaFile.objects.create(
            storage_key=f"media/{uuid4().hex}.png",
            original_name="structure.png",
            mime_type="image/png",
            size_bytes=2048,
        )
        return ContentBlock, media, _create_draft_image_block(media)

    def test_delete_is_refused_when_the_publish_committed_first(self):
        """The delete holds no lock yet while the publish commits.

        The delete request is paused after the view read the media row and before
        the deletion service takes its row lock, so the publish commits a new
        published reference in between. The content-owned guard must then refuse
        the delete with 409 ``CONTENT_CONFLICT`` and the media row must survive
        with its published reference intact.
        """

        ContentBlock, media, block = self._media_with_draft_block()
        delete_client = _author_client("concurrency-deleter")
        publish_client = _author_client("concurrency-publisher")

        delete_started = threading.Event()
        release_delete = threading.Event()
        publish_committed = threading.Event()
        results: dict[str, tuple[int, str | None]] = {}

        real_get_media_or_404 = media_views._get_media_or_404
        real_finalize = APIView.finalize_response

        def gated_get_media_or_404(pk):
            """Hold the delete request open before the deletion service runs."""

            media_row = real_get_media_or_404(pk)
            delete_started.set()
            release_delete.wait(timeout=10)
            return media_row

        def signalling_finalize(view, request, response, *args, **kwargs):
            """Signal once the publish response is finalized, i.e. committed."""

            response = real_finalize(view, request, response, *args, **kwargs)
            if str(request.path).startswith(BLOCKS_URL):
                publish_committed.set()
            return response

        def run_delete():
            try:
                results["delete"] = _outcome(
                    delete_client.delete(f"{MEDIA_URL}{media.pk}/")
                )
            finally:
                connections.close_all()

        def run_publish():
            try:
                results["publish"] = _outcome(
                    publish_client.patch(
                        f"{BLOCKS_URL}{block.pk}/",
                        {"status": PUBLISHED},
                        format="json",
                    )
                )
            finally:
                connections.close_all()

        with (
            mock.patch.object(media_views, "_get_media_or_404", gated_get_media_or_404),
            mock.patch.object(APIView, "finalize_response", signalling_finalize),
        ):
            delete_thread = threading.Thread(target=run_delete)
            delete_thread.start()
            self.assertTrue(
                delete_started.wait(timeout=10),
                "the delete request never started",
            )
            publish_thread = threading.Thread(target=run_publish)
            publish_thread.start()
            publish_committed_seen = publish_committed.wait(timeout=10)
            release_delete.set()
            delete_thread.join(timeout=15)
            publish_thread.join(timeout=15)

        self.assertFalse(delete_thread.is_alive(), "the delete did not finish")
        self.assertFalse(publish_thread.is_alive(), "the publish did not finish")
        self.assertTrue(
            publish_committed_seen,
            "the publish did not commit while the delete transaction was open",
        )
        self.assertEqual(set(results), {"delete", "publish"})
        self.assertEqual(results["delete"], (409, "CONTENT_CONFLICT"))
        self.assertEqual(results["publish"], (200, None))

        block.refresh_from_db()
        self.assertEqual(block.status, PUBLISHED)
        self.assertEqual(block.media_id, media.pk)
        self.assertTrue(MediaFile.objects.filter(pk=media.pk).exists())
        self.assertFalse(
            ContentBlock.objects.filter(status=PUBLISHED, media__isnull=True).exists(),
            "a published block was left without its media",
        )

    def test_publish_cannot_slip_between_the_guard_and_the_delete(self):
        """The gated delete still holds the media row lock the publish needs.

        The delete runs the content-owned guard and is then held open, so it
        holds the media row lock while the concurrent publish of the same media
        arrives. The publish therefore only proceeds after the delete committed:
        it finds the media row gone and answers 422 ``INVALID_RELATION``, and the
        delete wins with 204. Without the media row lock in ``save_content_block``
        the publish commits in that window instead and the ``SET_NULL`` cascade
        of the delete detaches it, leaving a published block without its media.
        """

        ContentBlock, media, block = self._media_with_draft_block()
        delete_client = _author_client("guarded-deleter")
        publish_client = _author_client("guarded-publisher")

        guard_passed = threading.Event()
        release_delete = threading.Event()
        publish_started = threading.Event()
        publish_committed = threading.Event()
        results: dict[str, tuple[int, str | None]] = {}

        real_load_guard = services._load_delete_guard
        real_initial = APIView.initial
        real_finalize = APIView.finalize_response

        def gated_load_guard():
            """Run the real guard, then hold the delete transaction open."""

            guard = real_load_guard()

            def guarded(locked):
                guard(locked)
                guard_passed.set()
                release_delete.wait(timeout=10)

            return guarded

        def signalling_initial(view, request, *args, **kwargs):
            result = real_initial(view, request, *args, **kwargs)
            if str(request.path).startswith(BLOCKS_URL):
                publish_started.set()
            return result

        def signalling_finalize(view, request, response, *args, **kwargs):
            response = real_finalize(view, request, response, *args, **kwargs)
            if str(request.path).startswith(BLOCKS_URL):
                publish_committed.set()
            return response

        def run_delete():
            try:
                results["delete"] = _outcome(
                    delete_client.delete(f"{MEDIA_URL}{media.pk}/")
                )
            finally:
                connections.close_all()

        def run_publish():
            try:
                results["publish"] = _outcome(
                    publish_client.patch(
                        f"{BLOCKS_URL}{block.pk}/",
                        {"status": PUBLISHED, "media": media.pk},
                        format="json",
                    )
                )
            finally:
                connections.close_all()

        with (
            mock.patch.object(services, "_load_delete_guard", gated_load_guard),
            mock.patch.object(APIView, "initial", signalling_initial),
            mock.patch.object(APIView, "finalize_response", signalling_finalize),
        ):
            delete_thread = threading.Thread(target=run_delete)
            delete_thread.start()
            self.assertTrue(
                guard_passed.wait(timeout=10),
                "the delete never passed the deletion guard",
            )
            publish_thread = threading.Thread(target=run_publish)
            publish_thread.start()
            self.assertTrue(
                publish_started.wait(timeout=10),
                "the publish request never started",
            )
            committed_while_gated = publish_committed.wait(timeout=2)
            release_delete.set()
            delete_thread.join(timeout=15)
            publish_thread.join(timeout=15)

        self.assertFalse(delete_thread.is_alive(), "the delete did not finish")
        self.assertFalse(publish_thread.is_alive(), "the publish did not finish")
        self.assertFalse(
            committed_while_gated,
            "the publish committed while the delete held the media row lock",
        )
        self.assertEqual(set(results), {"delete", "publish"})
        delete_status, delete_code = results["delete"]
        publish_status, publish_code = results["publish"]
        self.assertEqual((delete_status, delete_code), (204, None))
        self.assertNotEqual(
            publish_status,
            200,
            "the delete and the publish cannot both succeed",
        )
        self.assertIn(
            (publish_status, publish_code),
            {
                (422, "INVALID_RELATION"),
                (409, "CONTENT_CONFLICT"),
                (409, "INVALID_CONTENT_STATE"),
            },
        )

        block.refresh_from_db()
        self.assertNotEqual(block.status, PUBLISHED)
        self.assertIsNone(block.media_id)
        self.assertFalse(
            ContentBlock.objects.filter(status=PUBLISHED, media__isnull=True).exists(),
            "a published block was left without its media",
        )

    def test_publish_is_refused_when_the_delete_committed_first(self):
        """The mirror direction: the delete wins the race.

        The publish request is paused before it reads the block, the delete
        commits, and the publish must then observe the detached reference and
        refuse with the documented 409 ``INVALID_CONTENT_STATE``.
        """

        ContentBlock, media, block = self._media_with_draft_block()
        publish_client = _author_client("concurrency-publisher-first")
        delete_client = _author_client("concurrency-deleter-second")

        publish_started = threading.Event()
        release_publish = threading.Event()
        results: dict[str, tuple[int, str | None]] = {}

        real_initial = APIView.initial

        def gated_initial(view, request, *args, **kwargs):
            """Hold the publish request after authentication, before its read."""

            result = real_initial(view, request, *args, **kwargs)
            if str(request.path).startswith(BLOCKS_URL):
                publish_started.set()
                release_publish.wait(timeout=10)
            return result

        def run_publish():
            try:
                results["publish"] = _outcome(
                    publish_client.patch(
                        f"{BLOCKS_URL}{block.pk}/",
                        {"status": PUBLISHED},
                        format="json",
                    )
                )
            finally:
                connections.close_all()

        with mock.patch.object(APIView, "initial", gated_initial):
            publish_thread = threading.Thread(target=run_publish)
            publish_thread.start()
            self.assertTrue(
                publish_started.wait(timeout=10),
                "the publish request never started",
            )
            results["delete"] = _outcome(
                delete_client.delete(f"{MEDIA_URL}{media.pk}/")
            )
            release_publish.set()
            publish_thread.join(timeout=15)

        self.assertFalse(publish_thread.is_alive(), "the publish did not finish")
        self.assertEqual(set(results), {"delete", "publish"})
        self.assertEqual(results["delete"], (204, None))
        self.assertEqual(results["publish"], (409, "INVALID_CONTENT_STATE"))

        block.refresh_from_db()
        self.assertNotEqual(block.status, PUBLISHED)
        self.assertIsNone(block.media_id)
        self.assertFalse(
            ContentBlock.objects.filter(status=PUBLISHED, media__isnull=True).exists(),
            "a published block was left without its media",
        )
