from __future__ import annotations

from django.conf import settings
from django.core.checks import Error, Tags, register


@register(Tags.security)
def check_local_storage_backend(app_configs, **kwargs) -> list[Error]:
    """Refuse the development filesystem backend outside ``DEBUG``.

    ``MEDIA_STORAGE_BACKEND=local`` stores media on the application filesystem,
    which does not survive a container restart or a multi-instance deployment.
    Production must select an S3-compatible backend, so selecting the local one
    with ``DEBUG=False`` is a deployment error rather than a silent degradation.
    """

    if settings.MEDIA_STORAGE_BACKEND == "local" and not settings.DEBUG:
        return [
            Error(
                "MEDIA_STORAGE_BACKEND=local is a development/test backend and "
                "must not be used with DEBUG=False.",
                hint=(
                    "Configure an S3-compatible object-storage backend: set "
                    "MEDIA_STORAGE_BACKEND=s3 and the MEDIA_S3_* settings."
                ),
                id="media.E001",
            )
        ]
    return []
