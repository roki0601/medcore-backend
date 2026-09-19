from django.contrib import admin

from .models import MediaFile


@admin.register(MediaFile)
class MediaFileAdmin(admin.ModelAdmin):
    list_display = ("id", "original_name", "mime_type", "visibility", "size_bytes")
    list_filter = ("visibility", "mime_type")
    search_fields = ("original_name", "storage_key")
    readonly_fields = ("created_at", "updated_at")
