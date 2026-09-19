from __future__ import annotations

from rest_framework import serializers

from apps.content.models import (
    ContentBlock,
    ContentBlockType,
    Section,
    Source,
    Subject,
    Topic,
)

TEXT_BLOCK_KEYS = ("markdown", "callout")
IMAGE_BLOCK_KEY = "image"


class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ("id", "title", "description", "slug", "position")


class SectionSerializer(serializers.ModelSerializer):
    subject = serializers.IntegerField(source="subject_id", read_only=True)

    class Meta:
        model = Section
        fields = ("id", "subject", "title", "description", "slug", "position")


class TopicSerializer(serializers.ModelSerializer):
    section = serializers.IntegerField(source="section_id", read_only=True)
    subject = serializers.IntegerField(source="section.subject_id", read_only=True)
    has_demo_preview = serializers.SerializerMethodField()

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
        )

    def get_has_demo_preview(self, obj: Topic) -> bool:
        annotated = getattr(obj, "has_demo_preview", None)
        if annotated is not None:
            return bool(annotated)
        return obj.blocks.filter(
            status=ContentBlock.Status.PUBLISHED,
            is_demo_preview=True,
        ).exists()


class SourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Source
        fields = ("id", "title", "source_type", "author", "year", "url", "note")


class MediaReferenceSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    mime_type = serializers.CharField()
    original_name = serializers.CharField()
    visibility = serializers.CharField()


class ContentBlockTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentBlockType
        fields = ("key", "title")


class ContentBlockSerializer(serializers.ModelSerializer):
    block_type = ContentBlockTypeSerializer(read_only=True)
    markdown_body = serializers.SerializerMethodField()
    media = serializers.SerializerMethodField()
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
        )

    def get_markdown_body(self, obj: ContentBlock) -> str | None:
        if obj.block_type.key in TEXT_BLOCK_KEYS:
            return obj.markdown_body
        return None

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
