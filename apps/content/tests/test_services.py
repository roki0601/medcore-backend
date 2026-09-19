from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import connections
from django.test import TransactionTestCase
from django.utils import timezone

from apps.common.exceptions import APIError
from apps.content import services
from apps.content.models import ContentBlock, ContentBlockType, Source, Subject, Topic
from apps.media.models import MediaFile


@pytest.mark.django_db
def test_positions_are_assigned_deterministically_per_parent():
    first = services.save_subject(title="Pharmacology")
    second = services.save_subject(title="Anatomy")
    assert (first.position, second.position) == (1, 2)

    section = services.save_section(first, title="Antibiotics")
    assert section.position == 1
    other_section = services.save_section(second, title="Bones")
    assert other_section.position == 1

    topic_one = services.save_topic(section, title="Beta-lactams")
    topic_two = services.save_topic(section, title="Macrolides")
    assert (topic_one.position, topic_two.position) == (1, 2)


@pytest.mark.django_db
def test_slug_collisions_get_a_deterministic_suffix():
    first = services.save_subject(title="Pharmacology")
    second = services.save_subject(title="Pharmacology")
    third = services.save_subject(title="Pharmacology")

    assert first.slug == "pharmacology"
    assert second.slug == "pharmacology-2"
    assert third.slug == "pharmacology-3"


@pytest.mark.django_db
def test_explicit_duplicate_position_is_rejected_as_conflict():
    subject = services.save_subject(title="Pharmacology")
    section = services.save_section(subject, title="Antibiotics")
    services.save_topic(section, title="Beta-lactams", position=1)

    with pytest.raises(APIError) as exc:
        services.save_topic(section, title="Macrolides", position=1)

    assert exc.value.default_code == "CONTENT_CONFLICT"
    assert exc.value.status_code == 409


@pytest.mark.django_db
def test_publish_sets_timestamp_and_reviewer_then_clears_on_unpublish(editor):
    subject = services.save_subject(title="Pharmacology")
    section = services.save_section(subject, title="Antibiotics")
    topic = services.save_topic(section, title="Beta-lactams")

    block = services.save_content_block(
        topic,
        block_type_key="markdown",
        markdown_body="# Theory",
        status=ContentBlock.Status.PUBLISHED,
        actor=editor,
    )
    assert block.published_at is not None
    assert block.published_at <= timezone.now()
    assert block.reviewed_by == editor

    unpublished = services.save_content_block(
        topic,
        block_type_key="markdown",
        markdown_body="# Theory",
        status=ContentBlock.Status.DRAFT,
        instance=block,
    )
    assert unpublished.published_at is None


@pytest.mark.django_db
def test_publish_preconditions_return_invalid_content_state():
    subject = services.save_subject(title="Pharmacology")
    section = services.save_section(subject, title="Antibiotics")
    topic = services.save_topic(section, title="Beta-lactams")

    with pytest.raises(APIError) as empty_markdown:
        services.save_content_block(
            topic,
            block_type_key="markdown",
            markdown_body="   ",
            status=ContentBlock.Status.PUBLISHED,
        )
    assert empty_markdown.value.default_code == "INVALID_CONTENT_STATE"

    with pytest.raises(APIError) as missing_media:
        services.save_content_block(
            topic,
            block_type_key="image",
            status=ContentBlock.Status.PUBLISHED,
        )
    assert missing_media.value.default_code == "INVALID_CONTENT_STATE"


@pytest.mark.django_db
def test_unknown_block_type_is_rejected():
    subject = services.save_subject(title="Pharmacology")
    section = services.save_section(subject, title="Antibiotics")
    topic = services.save_topic(section, title="Beta-lactams")

    with pytest.raises(APIError) as exc:
        services.save_content_block(topic, block_type_key="video")
    assert exc.value.default_code == "VALIDATION_ERROR"
    assert exc.value.status_code == 422


@pytest.mark.django_db
def test_image_block_keeps_safe_reference_and_never_a_storage_key():
    subject = services.save_subject(title="Pharmacology")
    section = services.save_section(subject, title="Antibiotics")
    topic = services.save_topic(section, title="Beta-lactams")
    media = MediaFile.objects.create(
        storage_key="k/secret.png",
        mime_type="image/png",
        size_bytes=42,
        visibility=MediaFile.Visibility.PROTECTED,
    )

    block = services.save_content_block(
        topic,
        block_type_key="image",
        media=media,
        status=ContentBlock.Status.PUBLISHED,
    )
    assert block.media == media


@pytest.mark.django_db
def test_source_attach_and_detach_never_delete_content(editor):
    subject = services.save_subject(title="Pharmacology")
    section = services.save_section(subject, title="Antibiotics")
    topic = services.save_topic(section, title="Beta-lactams")
    block = services.save_content_block(
        topic,
        block_type_key="markdown",
        markdown_body="# Theory",
    )
    source = services.save_source(
        title="Guideline",
        source_type=Source.SourceType.GUIDELINE,
        url="https://example.org/g",
    )

    services.attach_source(source, topic=topic, block=block)
    assert source.topics.filter(pk=topic.pk).exists()
    assert source.content_blocks.filter(pk=block.pk).exists()

    services.detach_source(source, topic=topic, block=block)
    assert not source.topics.exists()
    assert not source.content_blocks.exists()
    assert Topic.objects.filter(pk=topic.pk).exists()
    assert ContentBlock.objects.filter(pk=block.pk).exists()

    services.attach_source(source, topic=topic)
    source.delete()
    assert Topic.objects.filter(pk=topic.pk).exists()
    assert ContentBlock.objects.filter(pk=block.pk).exists()


@pytest.mark.django_db
def test_delete_topic_removes_only_its_aggregate():
    subject = services.save_subject(title="Pharmacology")
    section = services.save_section(subject, title="Antibiotics")
    target = services.save_topic(section, title="Beta-lactams")
    sibling = services.save_topic(section, title="Macrolides")
    services.save_content_block(
        target,
        block_type_key="markdown",
        markdown_body="# Theory",
    )
    services.save_content_block(
        sibling,
        block_type_key="markdown",
        markdown_body="# Other",
    )

    services.delete_topic(target)

    assert not Topic.objects.filter(pk=target.pk).exists()
    assert not ContentBlock.objects.filter(topic_id=target.pk).exists()
    assert Topic.objects.filter(pk=sibling.pk).exists()
    assert ContentBlock.objects.filter(topic=sibling).count() == 1
    assert Subject.objects.filter(pk=subject.pk).exists()


@pytest.mark.django_db
def test_service_rejects_raw_html_with_validation_error():
    subject = services.save_subject(title="Pharmacology")
    section = services.save_section(subject, title="Antibiotics")
    topic = services.save_topic(section, title="Beta-lactams")

    with pytest.raises(APIError) as raw_html:
        services.save_content_block(
            topic,
            block_type_key="markdown",
            markdown_body="<script>alert(1)</script>",
        )
    assert raw_html.value.default_code == "VALIDATION_ERROR"
    assert raw_html.value.status_code == 422
    assert "markdown_body" in raw_html.value.fields

    with pytest.raises(APIError) as blank_title:
        services.save_subject(title="   ")
    assert blank_title.value.default_code == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_moving_content_to_another_parent_reassigns_position():
    subject = services.save_subject(title="Pharmacology")
    other_subject = services.save_subject(title="Anatomy")
    first_section = services.save_section(subject, title="First")
    second_section = services.save_section(subject, title="Second")
    other_section = services.save_section(other_subject, title="Bones")

    services.save_section(other_subject, title="Joints")
    moved_section = services.save_section(
        other_subject, title="Moved", instance=first_section
    )
    assert moved_section.subject == other_subject
    assert moved_section.position == 3

    services.save_topic(second_section, title="Occupied")
    source_topic = services.save_topic(first_section, title="Moved")
    moved_topic = services.save_topic(
        second_section,
        title="Moved",
        instance=source_topic,
    )
    assert moved_topic.section == second_section
    assert moved_topic.position == 2

    first_topic = services.save_topic(other_section, title="First topic")
    target_topic = services.save_topic(other_section, title="Target topic")
    services.save_content_block(
        target_topic,
        block_type_key="markdown",
        markdown_body="# Occupied",
    )
    block = services.save_content_block(
        first_topic,
        block_type_key="markdown",
        markdown_body="# Moved",
    )
    moved_block = services.save_content_block(
        target_topic,
        block_type_key="markdown",
        markdown_body="# Moved",
        instance=block,
    )
    assert moved_block.topic == target_topic
    assert moved_block.position == 2


class ConcurrentTopicCreationTests(TransactionTestCase):
    """Real concurrent transactions for locked position assignment."""

    def test_concurrent_topic_creation_under_one_section_keeps_positions_unique(self):
        subject = services.save_subject(title="Pharmacology")
        section = services.save_section(subject, title="Antibiotics")

        def create(index: int) -> int:
            try:
                topic = services.save_topic(section, title=f"Topic {index}")
                return topic.position
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=4) as executor:
            positions = list(executor.map(create, range(4)))

        self.assertEqual(sorted(positions), [1, 2, 3, 4])
        self.assertEqual(Topic.objects.filter(section=section).count(), 4)
        self.assertEqual(len(set(positions)), 4)
        self.assertEqual(ContentBlockType.objects.filter(active=True).count(), 3)
