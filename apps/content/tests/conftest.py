from __future__ import annotations

from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import caches
from django.db.models import Max
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.content.models import (
    ContentBlock,
    ContentBlockType,
    Flashcard,
    Quiz,
    QuizAnswer,
    QuizQuestion,
    Section,
    Subject,
    Topic,
)
from apps.media.models import MediaFile

User = get_user_model()

BLOCK_TYPE_SEED = (
    ("markdown", "Markdown"),
    ("image", "Image"),
    ("callout", "Callout"),
)

INTEGRATION_API_KEY = "test-integration-key"


def _next_position(model, **filters) -> int:
    current = model.objects.filter(**filters).aggregate(value=Max("position"))["value"]
    return (current or 0) + 1


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
    settings.MEDCORE_CONTENT_API_KEY = INTEGRATION_API_KEY
    settings.STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
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
def integration_client(api_client, settings) -> APIClient:
    """An API client that sends the configured integration key."""

    api_client.credentials(
        HTTP_X_MEDCORE_INTEGRATION_KEY=settings.MEDCORE_CONTENT_API_KEY
    )
    return api_client


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


@pytest.fixture
def make_flashcard(db):
    def _make_flashcard(
        topic: Topic,
        *,
        question: str = "Which ring is strained?",
        answer: str = "The beta-lactam ring",
        position: int | None = None,
        external_id: str | None = None,
    ) -> Flashcard:
        if position is None:
            position = _next_position(Flashcard, topic=topic)
        return Flashcard.objects.create(
            topic=topic,
            question=question,
            answer=answer,
            position=position,
            external_id=external_id,
        )

    return _make_flashcard


@pytest.fixture
def make_quiz(db):
    def _make_quiz(
        topic: Topic,
        *,
        title: str = "Beta-lactams basics",
        description: str = "",
        position: int | None = None,
        external_id: str | None = None,
    ) -> Quiz:
        if position is None:
            position = _next_position(Quiz, topic=topic)
        return Quiz.objects.create(
            topic=topic,
            title=title,
            description=description,
            position=position,
            external_id=external_id,
        )

    return _make_quiz


@pytest.fixture
def make_quiz_question(db):
    def _make_quiz_question(
        quiz: Quiz,
        *,
        text: str = "Which of these are beta-lactams?",
        position: int | None = None,
    ) -> QuizQuestion:
        if position is None:
            position = _next_position(QuizQuestion, quiz=quiz)
        return QuizQuestion.objects.create(quiz=quiz, text=text, position=position)

    return _make_quiz_question


@pytest.fixture
def make_quiz_answer(db):
    def _make_quiz_answer(
        question: QuizQuestion,
        *,
        text: str = "Penicillin",
        is_correct: bool = False,
        position: int | None = None,
    ) -> QuizAnswer:
        if position is None:
            position = _next_position(QuizAnswer, question=question)
        return QuizAnswer.objects.create(
            question=question,
            text=text,
            is_correct=is_correct,
            position=position,
        )

    return _make_quiz_answer


@pytest.fixture
def published_image_block(db, catalog):
    """Create a media row and the image ContentBlock referencing it."""

    def _published_image_block(
        *,
        topic: Topic | None = None,
        position: int | None = None,
        status: str = ContentBlock.Status.PUBLISHED,
        demo: bool = False,
        visibility: str = MediaFile.Visibility.PROTECTED,
        size_bytes: int = 2048,
    ) -> tuple[MediaFile, ContentBlock]:
        if topic is None:
            section = catalog["section"]
            topic = catalog["add_topic"](
                title="Image topic",
                slug=f"image-topic-{uuid4().hex[:8]}",
                position=_next_position(Topic, section=section),
            )
        media = MediaFile.objects.create(
            storage_key=f"test-{uuid4().hex}",
            original_name="structure.png",
            mime_type="image/png",
            size_bytes=size_bytes,
            visibility=visibility,
        )
        if position is None:
            position = _next_position(ContentBlock, topic=topic)
        block = catalog["add_block"](
            topic,
            block_type="image",
            position=position,
            status=status,
            demo=demo,
            media=media,
        )
        return media, block

    return _published_image_block
