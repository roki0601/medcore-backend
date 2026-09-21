from __future__ import annotations

from typing import Any

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.common.exceptions import APIError
from apps.content import services
from apps.content.models import (
    ContentBlock,
    ContentBlockType,
    Flashcard,
    Quiz,
    QuizAnswer,
    QuizQuestion,
    Section,
    Source,
    Subject,
    Topic,
)
from apps.media.models import MediaFile

EXTERNAL_ID_MAX_LENGTH = 255
TEXT_BLOCK_KEYS = ("markdown", "callout")
IMAGE_BLOCK_KEY = "image"


class MediaReferenceSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    mime_type = serializers.CharField()
    original_name = serializers.CharField()
    visibility = serializers.CharField()


class SubjectSerializer(serializers.ModelSerializer):
    cover = serializers.SerializerMethodField(allow_null=True)

    class Meta:
        model = Subject
        fields = (
            "id",
            "title",
            "description",
            "slug",
            "position",
            "external_id",
            "cover",
        )

    @extend_schema_field(MediaReferenceSerializer(allow_null=True))
    def get_cover(self, obj: Subject) -> dict | None:
        if obj.cover_id is None:
            return None
        return MediaReferenceSerializer(obj.cover).data


class SectionSerializer(serializers.ModelSerializer):
    subject = serializers.IntegerField(source="subject_id", read_only=True)

    class Meta:
        model = Section
        fields = (
            "id",
            "subject",
            "title",
            "description",
            "slug",
            "position",
            "external_id",
        )


class TopicSerializer(serializers.ModelSerializer):
    section = serializers.IntegerField(source="section_id", read_only=True)
    subject = serializers.IntegerField(source="section.subject_id", read_only=True)
    has_demo_preview = serializers.SerializerMethodField()
    cover = serializers.SerializerMethodField(allow_null=True)

    class Meta:
        model = Topic
        fields = (
            "id",
            "section",
            "subject",
            "title",
            "description",
            "slug",
            "position",
            "status",
            "access_level",
            "has_demo_preview",
            "external_id",
            "cover",
        )

    def get_has_demo_preview(self, obj: Topic) -> bool:
        annotated = getattr(obj, "has_demo_preview", None)
        if annotated is not None:
            return bool(annotated)
        return obj.blocks.filter(
            status=ContentBlock.Status.PUBLISHED,
            is_demo_preview=True,
        ).exists()

    @extend_schema_field(MediaReferenceSerializer(allow_null=True))
    def get_cover(self, obj: Topic) -> dict | None:
        if obj.cover_id is None:
            return None
        return MediaReferenceSerializer(obj.cover).data


class SourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Source
        fields = (
            "id",
            "title",
            "source_type",
            "author",
            "year",
            "url",
            "note",
            "external_id",
        )


class ContentBlockTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentBlockType
        fields = ("key", "title")


class ContentBlockSerializer(serializers.ModelSerializer):
    block_type = ContentBlockTypeSerializer(read_only=True)
    markdown_body = serializers.SerializerMethodField()
    media = serializers.SerializerMethodField(allow_null=True)
    sources = SourceSerializer(many=True, read_only=True)

    class Meta:
        model = ContentBlock
        fields = (
            "id",
            "block_type",
            "position",
            "status",
            "is_demo_preview",
            "caption",
            "markdown_body",
            "media",
            "published_at",
            "sources",
            "external_id",
        )

    def get_markdown_body(self, obj: ContentBlock) -> str | None:
        if obj.block_type.key in TEXT_BLOCK_KEYS:
            return obj.markdown_body
        return None

    @extend_schema_field(MediaReferenceSerializer(allow_null=True))
    def get_media(self, obj: ContentBlock) -> dict | None:
        if obj.block_type.key != IMAGE_BLOCK_KEY or obj.media is None:
            return None
        return MediaReferenceSerializer(obj.media).data


class TopicAccessSerializer(serializers.Serializer):
    level = serializers.CharField()
    full_access = serializers.BooleanField()
    is_demo_preview = serializers.BooleanField()


class TopicContentSerializer(serializers.Serializer):
    topic = TopicSerializer()
    access = TopicAccessSerializer()
    sources = SourceSerializer(many=True)
    blocks = ContentBlockSerializer(many=True)


class SearchResultSerializer(serializers.Serializer):
    type = serializers.CharField()
    id = serializers.IntegerField()
    title = serializers.CharField()
    subject_id = serializers.IntegerField(allow_null=True)
    section_id = serializers.IntegerField(allow_null=True)
    access_level = serializers.CharField(allow_null=True, required=False)
    has_demo_preview = serializers.BooleanField(allow_null=True, required=False)


# ---------------------------------------------------------------------------
# 004 write layer: strict write serializers and the flashcard/quiz reads.
# ---------------------------------------------------------------------------


def _validation_fields(exc: serializers.ValidationError) -> dict[str, Any]:
    detail = exc.detail
    if isinstance(detail, dict):
        return {str(key): value for key, value in detail.items()}
    if isinstance(detail, list):
        return {"non_field_errors": detail}
    return {"non_field_errors": [detail]}


class StrictSerializerMixin:
    """Reject unknown keys and report failures in the content API envelope.

    DRF ignores unknown keys by default and reports its own ``ValidationError``
    as HTTP 400 ``INVALID_REQUEST``; the content API contract requires 422
    ``VALIDATION_ERROR`` with the offending keys in ``fields``.
    """

    def to_internal_value(self, data):
        if hasattr(data, "keys"):
            unknown = [key for key in data.keys() if key not in self.fields]
            if unknown:
                raise APIError(
                    "Request validation failed.",
                    code="VALIDATION_ERROR",
                    status_code=422,
                    fields={str(key): ["Unknown field."] for key in unknown},
                )
        return super().to_internal_value(data)

    def run_validation(self, data=serializers.empty):
        try:
            return super().run_validation(data)
        except APIError:
            raise
        except serializers.ValidationError as exc:
            raise APIError(
                "Request validation failed.",
                code="VALIDATION_ERROR",
                status_code=422,
                fields=_validation_fields(exc),
            ) from exc


class StrictWriteSerializer(StrictSerializerMixin, serializers.ModelSerializer):
    """Base for the content write payloads of the seven top-level entities.

    ``POST`` payloads carry the parent id (and, for a quiz, ``questions``).
    ``PATCH`` payloads are validated with ``partial=True``, which makes those
    fields optional and lets the view merge them from the addressed row; the
    payload minima of an existing aggregate are then decided by the service
    (409 ``CONTENT_CONFLICT``) rather than by the payload shape.
    """

    external_id = serializers.CharField(
        max_length=EXTERNAL_ID_MAX_LENGTH,
        allow_null=True,
        allow_blank=False,
        required=False,
    )

    def get_unique_together_validators(self):
        """Leave ``(parent, position)`` uniqueness to the write service.

        DRF would force an omitted ``position`` to be required and report a real
        duplicate as a 422 payload error; the service assigns the next position
        under a parent row lock and reports a duplicate as 409
        ``CONTENT_CONFLICT``.
        """

        return []


def _resolve_relation(model, value: int | None, field: str):
    if value is None:
        return None
    row = model.objects.filter(pk=value).first()
    if row is None:
        raise APIError(
            f"Unknown {field}.",
            code="INVALID_RELATION",
            status_code=422,
            fields={field: ["Unknown relation id."]},
        )
    return row


def _validate_relation_ids(model, values, field: str):
    """Validate one Source relation list and keep it as numeric ids.

    The write service takes ids and resolves them again inside its own
    transaction, so the serializer only proves that every id exists. An absent
    or explicitly null list stays ``None``, which leaves the relation untouched.
    """

    if values is None:
        return None
    requested = list(dict.fromkeys(values))
    if not requested:
        return []
    known = set(model.objects.filter(pk__in=requested).values_list("pk", flat=True))
    missing = [value for value in requested if value not in known]
    if missing:
        raise APIError(
            f"Unknown {field}.",
            code="INVALID_RELATION",
            status_code=422,
            fields={field: ["Unknown relation id."]},
        )
    return requested


class SubjectWriteSerializer(StrictWriteSerializer):
    cover = serializers.IntegerField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = Subject
        fields = ("title", "description", "position", "external_id", "cover")
        extra_kwargs = {
            "description": {"required": False},
            "position": {"required": False},
        }

    def validate_cover(self, value: int | None):
        return _resolve_relation(MediaFile, value, "cover")


class SectionWriteSerializer(StrictWriteSerializer):
    subject = serializers.IntegerField(write_only=True)

    class Meta:
        model = Section
        fields = ("subject", "title", "description", "position", "external_id")
        extra_kwargs = {
            "description": {"required": False},
            "position": {"required": False},
        }

    def validate_subject(self, value: int) -> Subject:
        return _resolve_relation(Subject, value, "subject")


class TopicWriteSerializer(StrictWriteSerializer):
    section = serializers.IntegerField(write_only=True)
    cover = serializers.IntegerField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = Topic
        fields = (
            "section",
            "title",
            "description",
            "position",
            "status",
            "access_level",
            "external_id",
            "cover",
        )
        extra_kwargs = {
            "description": {"required": False},
            "position": {"required": False},
        }

    def validate_section(self, value: int) -> Section:
        return _resolve_relation(Section, value, "section")

    def validate_cover(self, value: int | None):
        return _resolve_relation(MediaFile, value, "cover")


class ContentBlockWriteSerializer(StrictWriteSerializer):
    topic = serializers.IntegerField(write_only=True)
    block_type = serializers.CharField(max_length=64, write_only=True)
    media = serializers.IntegerField(
        write_only=True,
        required=False,
        allow_null=True,
    )

    class Meta:
        model = ContentBlock
        fields = (
            "topic",
            "block_type",
            "markdown_body",
            "media",
            "caption",
            "position",
            "status",
            "is_demo_preview",
            "external_id",
        )
        extra_kwargs = {
            "markdown_body": {"required": False},
            "caption": {"required": False},
            "position": {"required": False},
            "is_demo_preview": {"required": False},
        }

    def validate_topic(self, value: int) -> Topic:
        return _resolve_relation(Topic, value, "topic")

    def validate_block_type(self, value: str) -> ContentBlockType:
        return services.resolve_block_type(value)

    def validate_media(self, value: int | None):
        return _resolve_relation(MediaFile, value, "media")


class FlashcardWriteSerializer(StrictWriteSerializer):
    topic = serializers.IntegerField(write_only=True)

    class Meta:
        model = Flashcard
        fields = ("topic", "question", "answer", "position", "external_id")
        extra_kwargs = {"position": {"required": False}}

    def validate_topic(self, value: int) -> Topic:
        return _resolve_relation(Topic, value, "topic")


class QuizAnswerWriteSerializer(StrictSerializerMixin, serializers.Serializer):
    id = serializers.IntegerField(required=False)
    text = serializers.CharField(allow_blank=False)
    is_correct = serializers.BooleanField(required=False)
    position = serializers.IntegerField(required=False, min_value=0)


class QuizQuestionWriteSerializer(StrictSerializerMixin, serializers.Serializer):
    id = serializers.IntegerField(required=False)
    text = serializers.CharField(allow_blank=False)
    position = serializers.IntegerField(required=False, min_value=0)
    answers = QuizAnswerWriteSerializer(many=True, required=False)


class QuizWriteSerializer(StrictWriteSerializer):
    topic = serializers.IntegerField(write_only=True)
    questions = QuizQuestionWriteSerializer(many=True)

    class Meta:
        model = Quiz
        fields = (
            "topic",
            "title",
            "description",
            "position",
            "questions",
            "external_id",
        )
        extra_kwargs = {
            "description": {"required": False},
            "position": {"required": False},
        }

    def validate_topic(self, value: int) -> Topic:
        return _resolve_relation(Topic, value, "topic")

    def validate_questions(self, value: list[dict]) -> list[dict]:
        """Reject a create payload that cannot satisfy the aggregate invariants.

        A partial (``PATCH``) payload is not judged here: it edits an existing
        aggregate, so a violation that survives the nested upsert is reported by
        the service as 409 ``CONTENT_CONFLICT``.
        """

        if self.partial:
            return value
        if not value:
            raise APIError(
                "A quiz requires at least one question.",
                code="VALIDATION_ERROR",
                status_code=422,
                fields={"questions": ["A quiz requires at least one question."]},
            )
        for index, question in enumerate(value):
            field = f"questions[{index}]"
            if not question["text"].strip():
                raise APIError(
                    "Request validation failed.",
                    code="VALIDATION_ERROR",
                    status_code=422,
                    fields={field: ["Question text may not be blank."]},
                )
            answers = question.get("answers") or []
            if len(answers) < 2:
                raise APIError(
                    "Request validation failed.",
                    code="VALIDATION_ERROR",
                    status_code=422,
                    fields={field: ["A question requires at least two answers."]},
                )
            if not any(answer.get("is_correct") for answer in answers):
                raise APIError(
                    "Request validation failed.",
                    code="VALIDATION_ERROR",
                    status_code=422,
                    fields={field: ["A question requires a correct answer."]},
                )
        return value


class SourceWriteSerializer(StrictWriteSerializer):
    topic_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        allow_null=True,
    )
    block_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        allow_null=True,
    )
    flashcard_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        allow_null=True,
    )
    question_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Source
        fields = (
            "title",
            "source_type",
            "author",
            "year",
            "url",
            "note",
            "topic_ids",
            "block_ids",
            "flashcard_ids",
            "question_ids",
            "external_id",
        )
        extra_kwargs = {
            "author": {"required": False},
            "year": {"required": False},
            "url": {"required": False},
            "note": {"required": False},
        }

    def validate_topic_ids(self, value):
        return _validate_relation_ids(Topic, value, "topic_ids")

    def validate_block_ids(self, value):
        return _validate_relation_ids(ContentBlock, value, "block_ids")

    def validate_flashcard_ids(self, value):
        return _validate_relation_ids(Flashcard, value, "flashcard_ids")

    def validate_question_ids(self, value):
        return _validate_relation_ids(QuizQuestion, value, "question_ids")


class FlashcardSerializer(serializers.ModelSerializer):
    topic = serializers.IntegerField(source="topic_id", read_only=True)

    class Meta:
        model = Flashcard
        fields = ("id", "topic", "question", "answer", "position", "external_id")


class QuizSerializer(serializers.ModelSerializer):
    topic = serializers.IntegerField(source="topic_id", read_only=True)

    class Meta:
        model = Quiz
        fields = ("id", "topic", "title", "description", "position", "external_id")


class QuizAnswerSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuizAnswer
        fields = ("id", "text", "is_correct", "position")


class QuizQuestionSerializer(serializers.ModelSerializer):
    answers = serializers.SerializerMethodField()

    class Meta:
        model = QuizQuestion
        fields = ("id", "text", "position", "answers")

    def get_answers(self, obj: QuizQuestion) -> list[dict]:
        ordered = obj.answers.all().order_by("position", "id")
        return QuizAnswerSerializer(ordered, many=True).data


class QuizDetailSerializer(serializers.ModelSerializer):
    topic = serializers.IntegerField(source="topic_id", read_only=True)
    questions = serializers.SerializerMethodField()

    class Meta:
        model = Quiz
        fields = (
            "id",
            "topic",
            "title",
            "description",
            "position",
            "external_id",
            "questions",
        )

    def get_questions(self, obj: Quiz) -> list[dict]:
        ordered = obj.questions.all().order_by("position", "id")
        return QuizQuestionSerializer(ordered, many=True).data


# ---------------------------------------------------------------------------
# 004 authoring reads: the raw block view and the Source relation view.
# ---------------------------------------------------------------------------


class ContentBlockAuthoringSerializer(serializers.ModelSerializer):
    """The authoring view of one ContentBlock.

    The public 002 read serializer hides the body of non-text blocks and expands
    ``media`` into a reference object; the authoring surface returns the stored
    values, so a client reads back exactly what it wrote. ``storage_key`` is
    never part of the representation.
    """

    topic = serializers.IntegerField(source="topic_id", read_only=True)
    block_type = serializers.CharField(source="block_type.key", read_only=True)
    media = serializers.IntegerField(source="media_id", read_only=True)

    class Meta:
        model = ContentBlock
        fields = (
            "id",
            "topic",
            "block_type",
            "position",
            "status",
            "is_demo_preview",
            "markdown_body",
            "media",
            "caption",
            "published_at",
            "external_id",
        )


class SourceAuthoringSerializer(SourceSerializer):
    """The ``Source`` fields plus its four relation id sets."""

    topic_ids = serializers.PrimaryKeyRelatedField(
        source="topics",
        many=True,
        read_only=True,
    )
    block_ids = serializers.PrimaryKeyRelatedField(
        source="content_blocks",
        many=True,
        read_only=True,
    )
    flashcard_ids = serializers.PrimaryKeyRelatedField(
        source="flashcards",
        many=True,
        read_only=True,
    )
    question_ids = serializers.PrimaryKeyRelatedField(
        source="questions",
        many=True,
        read_only=True,
    )

    class Meta(SourceSerializer.Meta):
        fields = SourceSerializer.Meta.fields + (
            "topic_ids",
            "block_ids",
            "flashcard_ids",
            "question_ids",
        )
