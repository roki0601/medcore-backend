from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import RefreshSession, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        (
            "MedCore",
            {
                "fields": (
                    "role",
                    "telegram_id",
                    "telegram_username",
                    "auth_version",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )
    readonly_fields = ("created_at", "updated_at")


@admin.register(RefreshSession)
class RefreshSessionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "jti",
        "expires_at",
        "revoked_at",
        "last_used_at",
    )
    readonly_fields = (
        "user",
        "jti",
        "auth_version",
        "expires_at",
        "revoked_at",
        "created_at",
        "last_used_at",
    )
