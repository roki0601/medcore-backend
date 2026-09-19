from __future__ import annotations

from django.contrib import admin

from apps.common.permissions import CONTENT_AUTHOR_ROLES

from .models import MediaFile


class MediaPermissionMixin:
    """Gate the media CMS on staff plus an editor/admin application role.

    The gate mirrors the content CMS: the integration principal never reaches
    Django Admin, and a staff user without an author role has no media access.
    """

    def _has_media_access(self, request) -> bool:
        user = request.user
        if not (user.is_active and user.is_staff):
            return False
        return bool(
            user.is_superuser or getattr(user, "role", None) in CONTENT_AUTHOR_ROLES
        )

    def has_module_permission(self, request) -> bool:
        return self._has_media_access(request)

    def has_view_permission(self, request, obj=None) -> bool:
        return self._has_media_access(request)

    def has_add_permission(self, request) -> bool:
        return self._has_media_access(request)

    def has_change_permission(self, request, obj=None) -> bool:
        return self._has_media_access(request)

    def has_delete_permission(self, request, obj=None) -> bool:
        return self._has_media_access(request)


@admin.register(MediaFile)
class MediaFileAdmin(MediaPermissionMixin, admin.ModelAdmin):
    list_display = ("id", "original_name", "mime_type", "visibility", "size_bytes")
    list_filter = ("visibility", "mime_type")
    search_fields = ("original_name", "storage_key")
    readonly_fields = ("storage_key", "created_at", "updated_at")
