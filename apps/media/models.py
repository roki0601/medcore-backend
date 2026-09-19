from __future__ import annotations

from django.db import models

VISIBILITY_VALUES = ("public", "protected")


class MediaFile(models.Model):
    """Opaque metadata for a stored binary object.

    Feature 002 only needs this row as the ``ContentBlock.media`` foreign-key
    target. Upload, access URLs and the object-storage adapter belong to the
    media/content API feature (spec 004); a row here is not proof that a storage
    object exists.
    """

    class Visibility(models.TextChoices):
        PUBLIC = "public", "Public"
        PROTECTED = "protected", "Protected"

    storage_key = models.CharField(max_length=512, unique=True)
    original_name = models.CharField(max_length=255, blank=True, default="")
    mime_type = models.CharField(max_length=127)
    size_bytes = models.BigIntegerField()
    checksum = models.CharField(max_length=128, blank=True, default="")
    visibility = models.CharField(
        max_length=16,
        choices=Visibility.choices,
        default=Visibility.PROTECTED,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("id",)
        constraints = [
            models.CheckConstraint(
                condition=models.Q(size_bytes__gte=0),
                name="media_mediafile_size_non_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(visibility__in=VISIBILITY_VALUES),
                name="media_mediafile_visibility_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"MediaFile {self.pk}"
