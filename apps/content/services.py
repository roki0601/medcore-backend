from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, models, transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.common.exceptions import APIError
from apps.content.models import (
    ContentBlock,
    ContentBlockType,
    Section,
    Source,
    Subject,
    Topic,
)

MAX_SLUG_LENGTH = 255
SLUG_ATTEMPTS = 3
TEXT_BLOCK_KEYS = ("markdown", "callout")
IMAGE_BLOCK_KEY = "image"


def _unique_slug(model, title: str, *, instance=None) -> str:
    base = slugify(title)[:MAX_SLUG_LENGTH] or model._meta.model_name
    queryset = model.objects.all()
    if instance is not None and instance.pk is not None:
        queryset = queryset.exclude(pk=instance.pk)
    candidate = base
    suffix = 2
    while queryset.filter(slug=candidate).exists():
        tail = f"-{suffix}"
        candidate = f"{base[: MAX_SLUG_LENGTH - len(tail)]}{tail}"
        suffix += 1
    return candidate


def _next_position(model, parent, parent_field: str) -> int:
    queryset = model.objects.all()
    if parent is not None:
        queryset = queryset.filter(**{parent_field: parent})
    current = queryset.aggregate(value=models.Max("position"))["value"]
    return (current or 0) + 1


def _parent_changed(model, instance, parent, parent_field: str) -> bool:
    if instance.pk is None or parent is None or not parent_field:
        return False
    stored = (
        model.objects.filter(pk=instance.pk)
        .values_list(f"{parent_field}_id", flat=True)
        .first()
    )
    return stored is not None and stored != parent.pk


def _assert_position_free(
    model, instance, position: int, parent, parent_field: str
) -> None:
    conflict = model.objects.all()
    if parent is not None:
        conflict = conflict.filter(**{parent_field: parent})
    conflict = conflict.filter(position=position)
    if instance.pk is not None:
        conflict = conflict.exclude(pk=instance.pk)
    if conflict.exists():
        raise APIError(
            "Position is already in use.",
            code="CONTENT_CONFLICT",
            status_code=409,
        )


def _assign_position(model, instance, *, explicit_position, parent, parent_field):
    """Assign a deterministic position, re-assigning when the parent changed."""

    if instance.pk is None:
        if explicit_position is not None:
            _assert_position_free(
                model, instance, explicit_position, parent, parent_field
            )
            instance.position = explicit_position
        else:
            instance.position = _next_position(model, parent, parent_field)
        return
    if _parent_changed(model, instance, parent, parent_field):
        # Moving to another parent would keep a stale per-parent position.
        instance.position = _next_position(model, parent, parent_field)
        return
    if explicit_position is not None:
        _assert_position_free(model, instance, explicit_position, parent, parent_field)
        instance.position = explicit_position


def _validation_error(exc: DjangoValidationError) -> APIError:
    fields = getattr(exc, "message_dict", None) or {"non_field_errors": exc.messages}
    return APIError(
        "Request validation failed.",
        code="VALIDATION_ERROR",
        status_code=422,
        fields=fields,
    )


def _save_instance(instance, *, model, title: str, with_slug: bool = True):
    """Persist with a deterministic slug, retrying on a concurrent slug race."""

    last_error: IntegrityError | None = None
    for _ in range(SLUG_ATTEMPTS):
        if with_slug:
            instance.slug = _unique_slug(model, title, instance=instance)
        try:
            instance.full_clean(validate_unique=False, validate_constraints=False)
        except DjangoValidationError as exc:
            raise _validation_error(exc) from exc
        try:
            with transaction.atomic():
                instance.save()
            return instance
        except IntegrityError as exc:
            last_error = exc
    raise APIError(
        "Content conflict while saving.",
        code="CONTENT_CONFLICT",
        status_code=409,
    ) from last_error


def save_subject(
    *,
    title: str,
    description: str = "",
    position: int | None = None,
    instance: Subject | None = None,
) -> Subject:
    subject = instance or Subject()
    with transaction.atomic():
        subject.title = title
        subject.description = description
        _assign_position(
            Subject,
            subject,
            explicit_position=position,
            parent=None,
            parent_field="",
        )
        return _save_instance(subject, model=Subject, title=title)


def save_section(
    subject: Subject,
    *,
    title: str,
    description: str = "",
    position: int | None = None,
    instance: Section | None = None,
) -> Section:
    section = instance or Section()
    with transaction.atomic():
        Subject.objects.select_for_update().get(pk=subject.pk)
        section.subject = subject
        section.title = title
        section.description = description
        _assign_position(
            Section,
            section,
            explicit_position=position,
            parent=subject,
            parent_field="subject",
        )
        return _save_instance(section, model=Section, title=title)


def save_topic(
    section: Section,
    *,
    title: str,
    description: str = "",
    position: int | None = None,
    status: str = Topic.Status.DRAFT,
    access_level: str = Topic.AccessLevel.DEMO,
    instance: Topic | None = None,
) -> Topic:
    topic = instance or Topic()
    with transaction.atomic():
        Section.objects.select_for_update().get(pk=section.pk)
        topic.section = section
        topic.title = title
        topic.description = description
        topic.status = status
        topic.access_level = access_level
        _assign_position(
            Topic,
            topic,
            explicit_position=position,
            parent=section,
            parent_field="section",
        )
        return _save_instance(topic, model=Topic, title=title)


def publish_topic(topic: Topic) -> Topic:
    with transaction.atomic():
        locked = Topic.objects.select_for_update().get(pk=topic.pk)
        locked.status = Topic.Status.PUBLISHED
        locked.full_clean(validate_unique=False, validate_constraints=False)
        locked.save()
    return locked


def delete_topic(topic: Topic) -> None:
    """Delete the Topic aggregate and its owned children in one transaction."""

    with transaction.atomic():
        locked = Topic.objects.select_for_update().get(pk=topic.pk)
        locked.delete()


def resolve_block_type(block_type_key: str) -> ContentBlockType:
    try:
        return ContentBlockType.objects.get(key=block_type_key, active=True)
    except ContentBlockType.DoesNotExist as exc:
        raise APIError(
            "Unknown or inactive block type.",
            code="VALIDATION_ERROR",
            status_code=422,
        ) from exc


def _validate_publishable(block: ContentBlock) -> None:
    key = block.block_type.key
    if key in TEXT_BLOCK_KEYS:
        if not block.markdown_body.strip():
            raise APIError(
                "Markdown body is required for this block type.",
                code="INVALID_CONTENT_STATE",
                status_code=409,
            )
        return
    if key == IMAGE_BLOCK_KEY:
        if block.media is None:
            raise APIError(
                "A media reference is required for an image block.",
                code="INVALID_CONTENT_STATE",
                status_code=409,
            )
        return
    raise APIError(
        "Block type cannot be published.",
        code="INVALID_CONTENT_STATE",
        status_code=409,
    )


def _apply_status(block: ContentBlock, actor=None) -> None:
    if block.status == ContentBlock.Status.PUBLISHED:
        _validate_publishable(block)
        if block.published_at is None:
            block.published_at = timezone.now()
        if actor is not None and block.reviewed_by is None:
            block.reviewed_by = actor
    else:
        block.published_at = None


def save_content_block(
    topic: Topic,
    *,
    block_type_key: str,
    markdown_body: str = "",
    media=None,
    caption: str = "",
    position: int | None = None,
    status: str = ContentBlock.Status.DRAFT,
    is_demo_preview: bool = False,
    actor=None,
    instance: ContentBlock | None = None,
) -> ContentBlock:
    block = instance or ContentBlock()
    block_type = resolve_block_type(block_type_key)
    with transaction.atomic():
        Topic.objects.select_for_update().get(pk=topic.pk)
        block.topic = topic
        block.block_type = block_type
        block.markdown_body = markdown_body
        block.media = media
        block.caption = caption
        block.status = status
        block.is_demo_preview = is_demo_preview
        _assign_position(
            ContentBlock,
            block,
            explicit_position=position,
            parent=topic,
            parent_field="topic",
        )
        _apply_status(block, actor)
        return _save_instance(
            block,
            model=ContentBlock,
            title=topic.title,
            with_slug=False,
        )


def publish_content_block(block: ContentBlock, *, actor=None) -> ContentBlock:
    with transaction.atomic():
        locked = ContentBlock.objects.select_for_update().get(pk=block.pk)
        locked.status = ContentBlock.Status.PUBLISHED
        _apply_status(locked, actor)
        locked.full_clean(validate_unique=False, validate_constraints=False)
        locked.save()
    return locked


def save_source(
    *,
    title: str,
    source_type: str,
    author: str = "",
    year: int | None = None,
    url: str = "",
    note: str = "",
    instance: Source | None = None,
) -> Source:
    source = instance or Source()
    source.title = title
    source.source_type = source_type
    source.author = author
    source.year = year
    source.url = url
    source.note = note
    try:
        source.full_clean(validate_unique=False, validate_constraints=False)
    except DjangoValidationError as exc:
        raise _validation_error(exc) from exc
    source.save()
    return source


def attach_source(
    source: Source,
    *,
    topic: Topic | None = None,
    block: ContentBlock | None = None,
) -> None:
    with transaction.atomic():
        if topic is not None:
            source.topics.add(topic)
        if block is not None:
            source.content_blocks.add(block)


def detach_source(
    source: Source,
    *,
    topic: Topic | None = None,
    block: ContentBlock | None = None,
) -> None:
    with transaction.atomic():
        if topic is not None:
            source.topics.remove(topic)
        if block is not None:
            source.content_blocks.remove(block)
