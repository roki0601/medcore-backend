from __future__ import annotations

from django.contrib import admin

from .models import Payment, Plan, Subscription


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "code",
        "price_rub",
        "duration_days",
        "is_active",
        "created_at",
    )
    list_filter = ("is_active",)
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
        "created_at",
    )
    list_filter = ("status", "plan")
    search_fields = ("user__username", "user__email", "plan__title", "plan__code")
    raw_id_fields = ("user",)
    date_hierarchy = "expires_at"


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "plan",
        "amount",
        "status",
        "provider",
        "created_at",
        "paid_at",
    )
    list_filter = ("status", "provider", "created_at", "paid_at")
    search_fields = ("id", "user__username", "user__email", "plan__code")
    raw_id_fields = ("user", "plan", "subscription")
    readonly_fields = ("created_at", "updated_at", "paid_at")
    date_hierarchy = "created_at"
