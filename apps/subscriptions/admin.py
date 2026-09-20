from __future__ import annotations

from django.contrib import admin

from .models import Plan, Subscription


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "code",
        "price_rub",
        "duration_days",
        "is_active",
        "is_trial",
        "created_at",
    )
    list_filter = ("is_active", "is_trial")
    search_fields = ("title", "code", "description")
    prepopulated_fields = {"code": ("title",)}


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "plan",
        "status",
        "starts_at",
        "expires_at",
        "is_trial",
        "created_at",
    )
    list_filter = ("status", "is_trial", "plan")
    search_fields = ("user__username", "user__email", "plan__title", "plan__code")
    raw_id_fields = ("user",)
    date_hierarchy = "expires_at"
