from django.core.checks import Tags
from django.test import override_settings

from apps.media.checks import check_storage_configuration


def test_unknown_media_backend_fails_system_check(settings):
    settings.MEDIA_STORAGE_BACKEND = "filesystem"

    errors = check_storage_configuration(None, tags=[Tags.security])

    assert [error.id for error in errors] == ["media.E002"]


@override_settings(
    MEDIA_STORAGE_BACKEND="s3",
    MEDIA_S3_BUCKET="",
    MEDIA_S3_ACCESS_KEY="access",
    MEDIA_S3_SECRET_KEY="",
)
def test_s3_requires_bucket_and_credentials():
    errors = check_storage_configuration(None, tags=[Tags.security])

    assert [error.id for error in errors] == ["media.E003"]
    assert "MEDIA_S3_BUCKET" in errors[0].msg
    assert "MEDIA_S3_SECRET_KEY" in errors[0].msg


@override_settings(
    MEDIA_STORAGE_BACKEND="s3",
    MEDIA_S3_BUCKET="bucket",
    MEDIA_S3_ACCESS_KEY="access",
    MEDIA_S3_SECRET_KEY="secret",
)
def test_complete_s3_configuration_passes_without_network_call():
    assert check_storage_configuration(None, tags=[Tags.security]) == []
