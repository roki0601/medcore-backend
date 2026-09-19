from __future__ import annotations

from uuid import uuid4

import pytest
from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.cache import caches
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.media.models import MediaFile
from apps.media.storage import get_storage_adapter

User = get_user_model()

INTEGRATION_API_KEY = "test-integration-key"

BLOCK_TYPE_SEED = (
    ("markdown", "Markdown"),
    ("image", "Image"),
    ("callout", "Callout"),
)


def _content_model(name: str):
    """Resolve one content model through Django's application registry.

    The media app never imports the content app, so the media tests reach the
    content rows they need for the access matrix and the deletion guard by
    runtime lookup instead of a static import.
    """

    return django_apps.get_model("content", name)


@pytest.fixture(autouse=True)
def configure_media_test_env(settings, tmp_path):
    """Point the media app at a per-test local storage root and locmem cache."""

    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "medcore-media-tests",
        }
    }
    settings.JWT_SIGNING_KEY = "test-jwt-signing-key-with-at-least-32-bytes"
    settings.MEDCORE_CONTENT_API_KEY = INTEGRATION_API_KEY
    settings.MEDIA_STORAGE_BACKEND = "local"
    settings.MEDIA_STORAGE_ROOT = str(tmp_path / "media-storage")
    from rest_framework_simplejwt.settings import api_settings

    api_settings.SIGNING_KEY = settings.JWT_SIGNING_KEY
    caches["default"].clear()
    get_storage_adapter.cache_clear()
    yield
    get_storage_adapter.cache_clear()


@pytest.fixture(autouse=True)
def block_types(db):
    """Keep the seeded block-type registry present for every media test."""

    ContentBlockType = _content_model("ContentBlockType")
    for key, title in BLOCK_TYPE_SEED:
        ContentBlockType.objects.get_or_create(
            key=key,
            defaults={"title": title, "active": True},
        )


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def authenticate():
    def _authenticate(client: APIClient, user) -> APIClient:
        access = RefreshToken.for_user(user).access_token
        access["auth_version"] = user.auth_version
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        return client

    return _authenticate


@pytest.fixture
def integration_client(settings) -> APIClient:
    """An API client that sends the configured integration key.

    It is a client of its own: sharing one client between the integration
    principal and an anonymous or JWT caller would leak the credentials of the
    first into the second request.
    """

    client = APIClient()
    client.credentials(HTTP_X_MEDCORE_INTEGRATION_KEY=settings.MEDCORE_CONTENT_API_KEY)
    return client


@pytest.fixture
def make_user(db):
    def _make_user(
        *,
        username: str = "reader",
        role: str = User.Role.USER,
        is_staff: bool = False,
        is_superuser: bool = False,
        is_active: bool = True,
    ):
        user = User(
            username=username,
            role=role,
            is_staff=is_staff,
            is_superuser=is_superuser,
            is_active=is_active,
        )
        user.set_unusable_password()
        user.save()
        return user

    return _make_user


@pytest.fixture
def editor(make_user):
    return make_user(username="editor", role=User.Role.EDITOR, is_staff=True)


@pytest.fixture
def admin_user(make_user):
    return make_user(username="admin", role=User.Role.ADMIN, is_staff=True)


@pytest.fixture
def media_file(db):
    def _media_file(
        *,
        storage_key: str | None = None,
        original_name: str = "structure.png",
        mime_type: str = "image/png",
        size_bytes: int = 2048,
        checksum: str = "",
        visibility: str = MediaFile.Visibility.PROTECTED,
    ) -> MediaFile:
        return MediaFile.objects.create(
            storage_key=storage_key or f"media-{uuid4().hex}",
            original_name=original_name,
            mime_type=mime_type,
            size_bytes=size_bytes,
            checksum=checksum,
            visibility=visibility,
        )

    return _media_file


@pytest.fixture
def stored_media(media_file):
    """Create a media row and store exactly its declared bytes."""

    def _stored_media(
        *,
        visibility: str = MediaFile.Visibility.PROTECTED,
        mime_type: str = "image/png",
        data: bytes | None = None,
        checksum: str = "",
        original_name: str = "structure.png",
    ) -> tuple[MediaFile, bytes]:
        payload = data if data is not None else b"\x89PNG" + b"0" * 2044
        media = media_file(
            original_name=original_name,
            mime_type=mime_type,
            size_bytes=len(payload),
            checksum=checksum,
            visibility=visibility,
        )
        get_storage_adapter().write_object(media.storage_key, payload, mime_type)
        return media, payload

    return _stored_media


@pytest.fixture
def media_reference(db):
    """Create an image ``ContentBlock`` referencing one media row.

    A factory so one test can build a published reference (the deletion guard
    and the access decision) and an unpublished one (the detach path).
    """

    def _media_reference(
        media: MediaFile,
        *,
        block_status: str = "published",
        topic_status: str = "published",
        access_level: str = "demo",
        is_demo_preview: bool = False,
    ):
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
            status=topic_status,
            access_level=access_level,
        )
        return ContentBlock.objects.create(
            topic=topic,
            block_type=block_type,
            position=1,
            status=block_status,
            is_demo_preview=is_demo_preview,
            media=media,
        )

    return _media_reference
