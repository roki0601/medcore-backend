from __future__ import annotations

from django.conf import settings
from django.core.checks import Error, Tags, Warning, register


@register(Tags.security)
def check_local_storage_backend(app_configs, **kwargs) -> list[Warning]:
    """Warn that local media is single-node filesystem storage.

    ``MEDIA_STORAGE_BACKEND=local`` is valid in production when
    ``MEDIA_STORAGE_ROOT`` is a persistent volume. It does not survive an
    unmounted container filesystem and cannot be shared by multiple app
    instances. S3 remains available for that case.
    """

    if settings.MEDIA_STORAGE_BACKEND == "local" and not settings.DEBUG:
        return [
            Warning(
                "MEDIA_STORAGE_BACKEND=local stores files on the application "
                "filesystem.",
                hint=(
                    "Mount a persistent volume at MEDIA_STORAGE_ROOT. Use "
                    "MEDIA_STORAGE_BACKEND=s3 when more than one app instance "
                    "must read the same objects."
                ),
                id="media.W001",
            )
        ]
    return []


@register(Tags.security)
def check_storage_configuration(app_configs, **kwargs) -> list[Error]:
    """Reject unknown backends and incomplete S3 configuration."""

    backend = str(getattr(settings, "MEDIA_STORAGE_BACKEND", "")).strip().lower()
    if backend not in {"local", "s3"}:
        return [
            Error(
                f"MEDIA_STORAGE_BACKEND={backend!r} is not supported.",
                hint="Set MEDIA_STORAGE_BACKEND to 'local' or 's3'.",
                id="media.E002",
            )
        ]

    if backend != "s3":
        return []

    missing = [
        name
        for name in (
            "MEDIA_S3_BUCKET",
            "MEDIA_S3_ACCESS_KEY",
            "MEDIA_S3_SECRET_KEY",
        )
        if not str(getattr(settings, name, "")).strip()
    ]
    if not missing:
        return []
    return [
        Error(
            "S3 media storage is missing required settings: " + ", ".join(missing),
            hint="Set the bucket and S3 credentials before starting the service.",
            id="media.E003",
        )
    ]
