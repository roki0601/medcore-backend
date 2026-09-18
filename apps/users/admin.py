from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


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
