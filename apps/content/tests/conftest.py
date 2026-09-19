from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import caches
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.content.models import ContentBlock, ContentBlockType, Section, Subject, Topic

User = get_user_model()

BLOCK_TYPE_SEED = (
    ("markdown", "Markdown"),
    ("image", "Image"),
    ("callout", "Callout"),
)


@pytest.fixture(autouse=True)
def block_types(db):
    """Keep the seeded block-type registry present for every content test.

    A ``TransactionTestCase`` flushes the database, which would otherwise drop
    the rows created by the seed data migration between runs.
    """

    for key, title in BLOCK_TYPE_SEED:
        ContentBlockType.objects.get_or_create(key=key, defaults={"title": title})


@pytest.fixture(autouse=True)
def configure_content_test_env(settings):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "medcore-content-tests",
        }
    }
    settings.JWT_SIGNING_KEY = "test-jwt-signing-key-with-at-least-32-bytes"
    from rest_framework_simplejwt.settings import api_settings

    api_settings.SIGNING_KEY = settings.JWT_SIGNING_KEY
    caches["default"].clear()


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
def catalog(db):
    """Subject → Section with demo/free/paid/draft topics and blocks."""

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

    def add_topic(
        *,
        title,
        slug,
        position,
        status=Topic.Status.PUBLISHED,
        access_level=Topic.AccessLevel.DEMO,
    ):
        return Topic.objects.create(
            section=section,
            title=title,
            slug=slug,
            position=position,
            status=status,
            access_level=access_level,
        )

    def add_block(
        topic,
        *,
        block_type,
        position,
        status=ContentBlock.Status.PUBLISHED,
        body="",
        demo=False,
        media=None,
    ):
        from apps.content.models import ContentBlockType

        return ContentBlock.objects.create(
            topic=topic,
            block_type=ContentBlockType.objects.get(key=block_type),
            position=position,
            status=status,
            markdown_body=body,
            is_demo_preview=demo,
            media=media,
        )

    return {
        "subject": subject,
        "section": section,
        "add_topic": add_topic,
        "add_block": add_block,
    }
