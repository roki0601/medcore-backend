from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.content.validators import validate_markdown_body


def validate_non_blank(value: str) -> None:
    if value is None or not value.strip():
        raise ValidationError("This field may not be blank.", code="blank")


ACCESS_LEVEL_VALUES = ("demo", "free", "paid")
TOPIC_STATUS_VALUES = ("draft", "published")
BLOCK_STATUS_VALUES = ("draft", "generated", "reviewed", "published")
SOURCE_TYPE_VALUES = (
    "textbook",
    "presentation",
    "article",
    "website",
    "guideline",
    "other",
)
TITLE_VALIDATORS = (validate_non_blank,)


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Subject(TimeStampedModel):
    title = models.CharField(max_length=255, validators=TITLE_VALIDATORS)
    description = models.TextField(blank=True, default="")
    slug = models.SlugField(max_length=255, unique=True)
    position = models.PositiveIntegerField()

    class Meta:
        ordering = ("position", "id")

    def __str__(self) -> str:
        return self.title


class Section(TimeStampedModel):
    subject = models.ForeignKey(
        Subject,
        on_delete=models.PROTECT,
        related_name="sections",
    )
    title = models.CharField(max_length=255, validators=TITLE_VALIDATORS)
    description = models.TextField(blank=True, default="")
    slug = models.SlugField(max_length=255, unique=True)
    position = models.PositiveIntegerField()

    class Meta:
        ordering = ("position", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("subject", "position"),
                name="content_section_unique_subject_position",
            ),
        ]

    def __str__(self) -> str:
        return self.title


class Topic(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"

    class AccessLevel(models.TextChoices):
        DEMO = "demo", "Demo"
        FREE = "free", "Free"
        PAID = "paid", "Paid"

    section = models.ForeignKey(
        Section,
        on_delete=models.PROTECT,
        related_name="topics",
    )
    title = models.CharField(max_length=255, validators=TITLE_VALIDATORS)
    description = models.TextField(blank=True, default="")
    slug = models.SlugField(max_length=255, unique=True)
    position = models.PositiveIntegerField()
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    access_level = models.CharField(
        max_length=16,
        choices=AccessLevel.choices,
        default=AccessLevel.DEMO,
    )

    class Meta:
        ordering = ("position", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("section", "position"),
                name="content_topic_unique_section_position",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=TOPIC_STATUS_VALUES),
                name="content_topic_status_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(access_level__in=ACCESS_LEVEL_VALUES),
                name="content_topic_access_level_valid",
            ),
        ]

    def __str__(self) -> str:
        return self.title


class ContentBlockType(models.Model):
    key = models.SlugField(max_length=64, unique=True)
    title = models.CharField(max_length=127, validators=TITLE_VALIDATORS)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ("key",)

    def __str__(self) -> str:
        return self.key


class ContentBlock(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        GENERATED = "generated", "Generated"
        REVIEWED = "reviewed", "Reviewed"
        PUBLISHED = "published", "Published"

    topic = models.ForeignKey(
        Topic,
        on_delete=models.CASCADE,
        related_name="blocks",
    )
    block_type = models.ForeignKey(
        ContentBlockType,
        on_delete=models.PROTECT,
        related_name="blocks",
    )
    position = models.PositiveIntegerField()
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    is_demo_preview = models.BooleanField(default=False)
    markdown_body = models.TextField(
        blank=True,
        default="",
        validators=(validate_markdown_body,),
    )
    media = models.ForeignKey(
        "media.MediaFile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="content_blocks",
    )
    caption = models.CharField(max_length=255, blank=True, default="")
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_content_blocks",
    )
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("position", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("topic", "position"),
                name="content_block_unique_topic_position",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=BLOCK_STATUS_VALUES),
                name="content_block_status_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"ContentBlock {self.pk}"


class Source(TimeStampedModel):
    class SourceType(models.TextChoices):
        TEXTBOOK = "textbook", "Textbook"
        PRESENTATION = "presentation", "Presentation"
        ARTICLE = "article", "Article"
        WEBSITE = "website", "Website"
        GUIDELINE = "guideline", "Guideline"
        OTHER = "other", "Other"

    title = models.CharField(max_length=255, validators=TITLE_VALIDATORS)
    source_type = models.CharField(max_length=32, choices=SourceType.choices)
    author = models.CharField(max_length=255, blank=True, default="")
    year = models.PositiveSmallIntegerField(null=True, blank=True)
    url = models.URLField(max_length=500, blank=True, default="")
    note = models.TextField(blank=True, default="")
    topics = models.ManyToManyField(
        Topic,
        blank=True,
        related_name="sources",
    )
    content_blocks = models.ManyToManyField(
        ContentBlock,
        blank=True,
        related_name="sources",
    )

    class Meta:
        ordering = ("id",)
        constraints = [
            models.CheckConstraint(
                condition=models.Q(source_type__in=SOURCE_TYPE_VALUES),
                name="content_source_type_valid",
            ),
        ]

    def __str__(self) -> str:
        return self.title
