from __future__ import annotations

import sys
from datetime import timedelta

import boto3
import pytest
from botocore.exceptions import ClientError
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

from apps.media import storage
from apps.media.storage import S3StorageAdapter

BUCKET = "medcore-media"


def _client_error(status_code: int, code: str) -> ClientError:
    return ClientError(
        {
            "Error": {"Code": code, "Message": "stub"},
            "ResponseMetadata": {"HTTPStatusCode": status_code},
        },
        "HeadObject",
    )


class _StubS3Client:
    """A minimal stand-in for ``boto3.client("s3")``."""

    def __init__(self) -> None:
        self.factory: dict | None = None
        self.presigned: list[dict] = []
        self.deleted: list[tuple[str, str]] = []
        self.head = {"ContentLength": 2048, "ContentType": "image/png"}
        self.head_error: ClientError | None = None

    def generate_presigned_url(self, operation, Params=None, ExpiresIn=None):
        self.presigned.append(
            {"operation": operation, "params": Params, "expires_in": ExpiresIn}
        )
        return f"https://storage.example/{Params['Key']}?X-Amz-Signature=stub"

    def head_object(self, Bucket=None, Key=None):
        if self.head_error is not None:
            raise self.head_error
        return self.head

    def delete_object(self, Bucket=None, Key=None):
        self.deleted.append((Bucket, Key))


@pytest.fixture
def s3_client(monkeypatch) -> _StubS3Client:
    """Replace ``boto3.client`` with a recording stub."""

    client = _StubS3Client()

    def _factory(service, **kwargs):
        client.factory = {"service": service, **kwargs}
        return client

    monkeypatch.setattr(boto3, "client", _factory)
    return client


@pytest.fixture
def s3_adapter() -> S3StorageAdapter:
    return S3StorageAdapter(
        endpoint_url="http://minio:9000",
        bucket=BUCKET,
        region="us-east-1",
        access_key="access-key",
        secret_key="secret-key",
        addressing_style="path",
    )


@pytest.mark.django_db
def test_upload_url_is_presigned_with_the_declared_metadata(
    s3_client,
    s3_adapter,
    media_file,
):
    media = media_file(size_bytes=2048)

    signed = s3_adapter.create_upload_url(media=media, base_url="http://testserver")

    call = s3_client.presigned[0]
    assert call["operation"] == "put_object"
    assert call["params"] == {
        "Bucket": BUCKET,
        "Key": media.storage_key,
        "ContentType": media.mime_type,
        "ContentLength": media.size_bytes,
    }
    assert call["expires_in"] == settings.MEDIA_UPLOAD_URL_TTL
    assert (
        signed.url
        == f"https://storage.example/{media.storage_key}?X-Amz-Signature=stub"
    )
    assert signed.method == "PUT"
    remaining = signed.expires_at - timezone.now()
    assert (
        timedelta(seconds=settings.MEDIA_UPLOAD_URL_TTL - 5)
        <= remaining
        <= timedelta(seconds=settings.MEDIA_UPLOAD_URL_TTL + 5)
    )


@pytest.mark.django_db
def test_access_url_is_presigned_for_the_get_operation(
    s3_client,
    s3_adapter,
    media_file,
):
    media = media_file()

    signed = s3_adapter.create_access_url(media=media, base_url="http://testserver")

    call = s3_client.presigned[0]
    assert call["operation"] == "get_object"
    assert call["params"] == {"Bucket": BUCKET, "Key": media.storage_key}
    assert call["expires_in"] == settings.MEDIA_ACCESS_URL_TTL
    assert signed.method == "GET"


def test_the_client_is_built_from_the_adapter_configuration(s3_client, s3_adapter):
    s3_adapter.delete_object("media/abc.png")

    assert s3_client.factory is not None
    assert s3_client.factory["service"] == "s3"
    assert s3_client.factory["endpoint_url"] == "http://minio:9000"
    assert s3_client.factory["region_name"] == "us-east-1"
    assert s3_client.factory["aws_access_key_id"] == "access-key"
    assert s3_client.factory["aws_secret_access_key"] == "secret-key"
    assert s3_client.factory["config"].s3 == {"addressing_style": "path"}
    assert s3_client.deleted == [(BUCKET, "media/abc.png")]


@pytest.mark.django_db
def test_verify_object_returns_none_for_a_missing_object(s3_client, s3_adapter):
    s3_client.head_error = _client_error(404, "NoSuchKey")

    assert s3_adapter.verify_object("media/missing.png") is None

    s3_client.head_error = _client_error(200, "NotFound")

    assert s3_adapter.verify_object("media/missing.png") is None


@pytest.mark.django_db
def test_verify_object_returns_the_head_metadata(s3_client, s3_adapter):
    metadata = s3_adapter.verify_object("media/present.png")

    assert metadata is not None
    assert metadata.size_bytes == 2048
    assert metadata.content_type == "image/png"


@pytest.mark.django_db
def test_verify_object_reraises_a_non_missing_client_error(s3_client, s3_adapter):
    s3_client.head_error = _client_error(403, "AccessDenied")

    with pytest.raises(ClientError):
        s3_adapter.verify_object("media/forbidden.png")


def test_missing_s3_sdk_is_a_configuration_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "boto3", None)

    with pytest.raises(ImproperlyConfigured) as excinfo:
        storage._load_s3_sdk()

    assert "storage-s3" in str(excinfo.value)


@pytest.mark.django_db
def test_get_storage_adapter_selects_the_s3_backend(settings):
    settings.MEDIA_STORAGE_BACKEND = "s3"
    settings.MEDIA_S3_BUCKET = BUCKET
    storage.get_storage_adapter.cache_clear()

    adapter = storage.get_storage_adapter()

    assert isinstance(adapter, S3StorageAdapter)
    assert adapter.bucket == BUCKET
    assert adapter.supports_controlled_upload is False


@pytest.mark.django_db
def test_unknown_backend_is_a_configuration_error(settings):
    settings.MEDIA_STORAGE_BACKEND = "ftp"
    storage.get_storage_adapter.cache_clear()

    with pytest.raises(ImproperlyConfigured):
        storage.get_storage_adapter()
