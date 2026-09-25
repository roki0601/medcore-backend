from __future__ import annotations

from django.contrib import admin

from .models import Feedback


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ("id", "type", "subject", "user", "status", "topic", "created_at")
    list_filter = ("status", "type", "created_at")
    search_fields = ("subject", "message", "contact", "user__username")
    ordering = ("-created_at",)
    readonly_fields = (
        "id",
        "type",
        "subject",
        "message",
        "user",
        "contact",
        "topic",
        "page_url",
        "created_at",
        "updated_at",
    )
    fields = (
        "type",
        "subject",
        "message",
        "user",
        "contact",
        "topic",
        "page_url",
        "status",
        "created_at",
        "updated_at",
    )
    actions = ("mark_reviewed", "mark_resolved")

    @admin.action(description="Mark selected feedback as reviewed")
    def mark_reviewed(self, request, queryset):
        queryset.update(status=Feedback.Status.REVIEWED)

    @admin.action(description="Mark selected feedback as resolved")
    def mark_resolved(self, request, queryset):
        queryset.update(status=Feedback.Status.RESOLVED)
