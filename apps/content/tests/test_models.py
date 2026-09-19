from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.content.models import ContentBlock, ContentBlockType, Section, Subject, Topic
from apps.content.validators import validate_markdown_body
from apps.media.models import MediaFile


def _subject(**overrides) -> Subject:
    data = {"title": "Pharmacology", "slug": "pharmacology", "position": 1}
    data.update(overrides)
    return Subject.objects.create(**data)


def _section(subject: Subject, **overrides) -> Section:
    data = {
        "subject": subject,
        "title": "Antibiotics",
        "slug": "antibiotics",
        "position": 1,
    }
    data.update(overrides)
    return Section.objects.create(**data)


def _topic(section: Section, **overrides) -> Topic:
    data = {
        "section": section,
        "title": "Beta-lactams",
        "slug": "beta-lactams",
        "position": 1,
    }
    data.update(overrides)
    return Topic.objects.create(**data)


def _block(topic: Topic, **overrides) -> ContentBlock:
    data = {
        "topic": topic,
        "block_type": ContentBlockType.objects.get(key="markdown"),
        "position": 1,
        "markdown_body": "body",
    }
    data.update(overrides)
    return ContentBlock.objects.create(**data)


@pytest.mark.django_db
def test_titles_reject_blank_and_whitespace_only():
    with pytest.raises(ValidationError):
        _subject(title="   ").full_clean()
    with pytest.raises(ValidationError):
        _subject(title="", slug="empty").full_clean()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "body",
    ["<script>alert(1)</script>", "<img src=x onerror=alert(1)>", "</p>"],
)
def test_markdown_body_rejects_raw_html(body):
    with pytest.raises(ValidationError):
        validate_markdown_body(body)


@pytest.mark.django_db
def test_markdown_body_rejects_unsafe_link_schemes():
    with pytest.raises(ValidationError):
        validate_markdown_body("[click](javascript:alert(1))")


@pytest.mark.django_db
@pytest.mark.parametrize(
    "body",
    [
        "Доза <5 мм и a < b",
        "```\n<script>sample</script>\n```",
        "# Normal **markdown** with [link](https://example.org)",
    ],
)
def test_markdown_body_accepts_prose_and_fenced_code(body):
    validate_markdown_body(body)


@pytest.mark.django_db
def test_slug_is_unique_per_model():
    _subject()
    with pytest.raises(IntegrityError), transaction.atomic():
        _subject(title="Other", slug="pharmacology")


@pytest.mark.django_db
def test_section_position_is_unique_within_subject():
    subject = _subject()
    _section(subject)
    with pytest.raises(IntegrityError), transaction.atomic():
        _section(subject, title="Other", slug="other", position=1)


@pytest.mark.django_db
def test_controlled_values_are_protected_by_database_constraints():
    topic = _topic(_section(_subject()))
    with pytest.raises(IntegrityError), transaction.atomic():
        Topic.objects.filter(pk=topic.pk).update(access_level="premium")


@pytest.mark.django_db
def test_topic_deletion_cascades_owned_blocks_and_keeps_siblings():
    section = _section(_subject())
    target = _topic(section, title="Target", slug="target", position=1)
    sibling = _topic(section, title="Sibling", slug="sibling", position=2)
    _block(target)
    _block(sibling, position=1)
    target_pk = target.pk

    target.delete()

    assert not ContentBlock.objects.filter(topic_id=target_pk).exists()
    assert ContentBlock.objects.filter(topic=sibling).count() == 1
    assert Section.objects.filter(pk=section.pk).exists()
    assert Subject.objects.filter(pk=section.subject_id).exists()


@pytest.mark.django_db
def test_subject_and_section_deletion_are_protected():
    subject = _subject()
    section = _section(subject)
    _topic(section)
    with pytest.raises(ProtectedError):
        subject.delete()
    with pytest.raises(ProtectedError):
        section.delete()


@pytest.mark.django_db
def test_deleting_media_detaches_block_reference():
    topic = _topic(_section(_subject()))
    media = MediaFile.objects.create(
        storage_key="k/1.png",
        mime_type="image/png",
        size_bytes=10,
    )
    block = _block(
        topic,
        block_type=ContentBlockType.objects.get(key="image"),
        markdown_body="",
        media=media,
    )

    media.delete()

    block.refresh_from_db()
    assert block.media is None
