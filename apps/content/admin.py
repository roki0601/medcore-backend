from __future__ import annotations

from django import forms
from django.contrib import admin

from apps.common.permissions import CONTENT_AUTHOR_ROLES
from apps.content.models import (
    ContentBlock,
    ContentBlockType,
    Section,
    Source,
    Subject,
    Topic,
)

from . import services


class ContentPermissionMixin:
    """Gate the content CMS on staff plus an editor/admin application role."""

    def _has_content_access(self, request) -> bool:
        user = request.user
        if not (user.is_active and user.is_staff):
            return False
        return bool(
            user.is_superuser or getattr(user, "role", None) in CONTENT_AUTHOR_ROLES
        )

    def has_module_permission(self, request) -> bool:
        return self._has_content_access(request)

    def has_view_permission(self, request, obj=None) -> bool:
        return self._has_content_access(request)

    def has_add_permission(self, request) -> bool:
        return self._has_content_access(request)

    def has_change_permission(self, request, obj=None) -> bool:
        return self._has_content_access(request)

    def has_delete_permission(self, request, obj=None) -> bool:
        return self._has_content_access(request)


class ContentBlockAdminForm(forms.ModelForm):
    class Meta:
        model = ContentBlock
        fields = (
            "topic",
            "block_type",
            "status",
            "is_demo_preview",
            "markdown_body",
            "media",
            "caption",
        )

    def clean(self):
        cleaned = super().clean()
        block_type = cleaned.get("block_type")
        status = cleaned.get("status")
        if block_type is None or status != ContentBlock.Status.PUBLISHED:
            return cleaned
        if block_type.key in services.TEXT_BLOCK_KEYS:
            if not (cleaned.get("markdown_body") or "").strip():
                self.add_error(
                    "markdown_body",
                    "Markdown body is required to publish this block.",
                )
        elif block_type.key == services.IMAGE_BLOCK_KEY:
            if cleaned.get("media") is None:
                self.add_error(
                    "media",
                    "A media reference is required to publish an image block.",
                )
        return cleaned


@admin.register(Subject)
class SubjectAdmin(ContentPermissionMixin, admin.ModelAdmin):
    list_display = ("id", "title", "position")
    search_fields = ("title", "slug")
    readonly_fields = ("slug", "position", "created_at", "updated_at")

    def save_model(self, request, obj, form, change) -> None:
        services.save_subject(
            title=form.cleaned_data["title"],
            description=form.cleaned_data.get("description") or "",
            instance=obj,
        )


@admin.register(Section)
class SectionAdmin(ContentPermissionMixin, admin.ModelAdmin):
    list_display = ("id", "title", "subject", "position")
    list_filter = ("subject",)
    search_fields = ("title", "slug")
    readonly_fields = ("slug", "position", "created_at", "updated_at")

    def save_model(self, request, obj, form, change) -> None:
        services.save_section(
            form.cleaned_data["subject"],
            title=form.cleaned_data["title"],
            description=form.cleaned_data.get("description") or "",
            instance=obj,
        )


@admin.register(Topic)
class TopicAdmin(ContentPermissionMixin, admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "section",
        "position",
        "status",
        "access_level",
    )
    list_filter = ("status", "access_level", "section__subject")
    search_fields = ("title", "slug")
    readonly_fields = ("slug", "position", "created_at", "updated_at")

    def save_model(self, request, obj, form, change) -> None:
        services.save_topic(
            form.cleaned_data["section"],
            title=form.cleaned_data["title"],
            description=form.cleaned_data.get("description") or "",
            status=form.cleaned_data["status"],
            access_level=form.cleaned_data["access_level"],
            instance=obj,
        )


@admin.register(ContentBlockType)
class ContentBlockTypeAdmin(ContentPermissionMixin, admin.ModelAdmin):
    list_display = ("id", "key", "title", "active")
    list_filter = ("active",)
    search_fields = ("key", "title")


@admin.register(ContentBlock)
class ContentBlockAdmin(ContentPermissionMixin, admin.ModelAdmin):
    form = ContentBlockAdminForm
    list_display = (
        "id",
        "topic",
        "block_type",
        "position",
        "status",
        "is_demo_preview",
    )
    list_filter = ("status", "block_type", "is_demo_preview")
    search_fields = ("topic__title", "caption")
    readonly_fields = ("published_at", "reviewed_by", "created_at", "updated_at")

    def save_model(self, request, obj, form, change) -> None:
        services.save_content_block(
            form.cleaned_data["topic"],
            block_type_key=form.cleaned_data["block_type"].key,
            markdown_body=form.cleaned_data.get("markdown_body") or "",
            media=form.cleaned_data.get("media"),
            caption=form.cleaned_data.get("caption") or "",
            status=form.cleaned_data["status"],
            is_demo_preview=form.cleaned_data.get("is_demo_preview", False),
            actor=request.user,
            instance=obj,
        )


@admin.register(Source)
class SourceAdmin(ContentPermissionMixin, admin.ModelAdmin):
    list_display = ("id", "title", "source_type", "year")
    list_filter = ("source_type",)
    search_fields = ("title", "author")
    filter_horizontal = ("topics", "content_blocks")

    def save_model(self, request, obj, form, change) -> None:
        services.save_source(
            title=form.cleaned_data["title"],
            source_type=form.cleaned_data["source_type"],
            author=form.cleaned_data.get("author") or "",
            year=form.cleaned_data.get("year"),
            url=form.cleaned_data.get("url") or "",
            note=form.cleaned_data.get("note") or "",
            instance=obj,
        )
