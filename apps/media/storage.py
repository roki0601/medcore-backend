from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any, BinaryIO, Protocol

from django.conf import settings
from django.core import signing
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

from apps.common.exceptions import APIError
from apps.media.models import MediaFile

UPLOAD_OPERATION = "upload"
DOWNLOAD_OPERATION = "download"
UPLOAD_METHOD = "PUT"
DOWNLOAD_METHOD = "GET"
UPLOAD_URL_PATH = "/api/v1/media/upload/{token}/"
ACCESS_URL_PATH = "/api/v1/media/file/{token}/"
META_SUFFIX = ".meta"

S3_EXTRA_MESSAGE = (
    "MEDIA_STORAGE_BACKEND=s3 requires the optional 'storage-s3' dependency "
    "group (boto3). Install it with `uv sync --extra storage-s3`."
)


@dataclass(frozen=True)
class ObjectMetadata:
    """Verified metadata of a stored object."""

    size_bytes: int
    content_type: str


@dataclass(frozen=True)
class SignedUrl:
    """A short-lived capability URL for one storage operation."""

    url: str
    method: str
    expires_at: datetime


class StorageAdapter(Protocol):
    """Provider-neutral object-storage contract used by the media services.

    ``supports_controlled_upload`` tells the caller whether the backend can
    accept an upload through the backend itself (the local dev/test backend) or
    whether the client uploads directly to the provider (S3 presigned ``PUT``).
    """

    supports_controlled_upload: bool

    def create_upload_url(self, *, media: MediaFile, base_url: str) -> SignedUrl: ...

    def create_access_url(self, *, media: MediaFile, base_url: str) -> SignedUrl: ...

    def verify_object(self, storage_key: str) -> ObjectMetadata | None: ...

    def delete_object(self, storage_key: str) -> None: ...


def _invalid_token() -> APIError:
    return APIError(
        "The capability token is invalid or expired.",
        code="AUTHENTICATION_REQUIRED",
        status_code=401,
    )


def decode_token(
    token: str,
    *,
    salt: str,
    expected_op: str,
    expected_method: str,
    max_age: int,
) -> dict[str, Any]:
    """Decode and validate a capability token issued by the local backend.

    The token is bound to one operation, one media id, one HTTP method and its
    expiry, so a token minted for an upload can never be replayed as a download
    or against another media row. Bad, expired or mismatched tokens raise 401
    ``AUTHENTICATION_REQUIRED``.
    """

    try:
        payload = signing.loads(token, salt=salt, max_age=max_age)
    except (signing.BadSignature, ValueError, TypeError) as exc:
        raise _invalid_token() from exc

    if (
        not isinstance(payload, Mapping)
        or payload.get("op") != expected_op
        or payload.get("method") != expected_method
        or not isinstance(payload.get("media"), int)
    ):
        raise _invalid_token()
    return dict(payload)


class LocalStorageAdapter:
    """Filesystem object storage for development and test.

    Objects live at ``<MEDIA_STORAGE_ROOT>/<storage_key>`` next to a JSON
    sidecar at ``<storage_key>.meta`` holding the verified content type and
    size, so ``verify_object`` reports real metadata instead of trusting the
    database row. Upload and read URLs point at the controlled endpoints
    ``PUT /api/v1/media/upload/{token}/`` and ``GET /api/v1/media/file/{token}/``
    and carry a capability token that never contains the storage key.

    This backend is refused outside ``DEBUG`` by the ``media.E001`` system check.
    """

    supports_controlled_upload = True

    def __init__(self, root: str) -> None:
        self.root = root

    def create_upload_url(self, *, media: MediaFile, base_url: str) -> SignedUrl:
        token, expires_at = self._sign(
            media,
            op=UPLOAD_OPERATION,
            method=UPLOAD_METHOD,
            salt=settings.MEDIA_UPLOAD_TOKEN_SALT,
            ttl=settings.MEDIA_UPLOAD_URL_TTL,
        )
        return SignedUrl(
            url=self._capability_url(base_url, UPLOAD_URL_PATH, token),
            method=UPLOAD_METHOD,
            expires_at=expires_at,
        )

    def create_access_url(self, *, media: MediaFile, base_url: str) -> SignedUrl:
        token, expires_at = self._sign(
            media,
            op=DOWNLOAD_OPERATION,
            method=DOWNLOAD_METHOD,
            salt=settings.MEDIA_ACCESS_TOKEN_SALT,
            ttl=settings.MEDIA_ACCESS_URL_TTL,
        )
        return SignedUrl(
            url=self._capability_url(base_url, ACCESS_URL_PATH, token),
            method=DOWNLOAD_METHOD,
            expires_at=expires_at,
        )

    def write_object(self, storage_key: str, data: bytes, content_type: str) -> None:
        """Store the uploaded bytes and its verified metadata sidecar.

        An existing object is never overwritten: re-uploading different bytes of
        the same declared size would otherwise silently invalidate the earlier
        verification, so a second write is refused with 422 ``MEDIA_INVALID``.
        """

        path = self._object_path(storage_key)
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        try:
            with open(path, "xb") as handle:
                handle.write(data)
        except FileExistsError as exc:
            raise APIError(
                "The object already exists.",
                code="MEDIA_INVALID",
                status_code=422,
            ) from exc
        with open(self._meta_path(storage_key), "w", encoding="utf-8") as handle:
            json.dump({"content_type": content_type, "size_bytes": len(data)}, handle)

    def read_object(self, storage_key: str) -> BinaryIO:
        """Return an open binary handle for the stored object."""

        return open(self._object_path(storage_key), "rb")

    def verify_object(self, storage_key: str) -> ObjectMetadata | None:
        """Return the sidecar metadata when the stored size still matches it."""

        metadata = self._read_metadata(storage_key)
        if metadata is None:
            return None
        try:
            stat = os.stat(self._object_path(storage_key))
        except FileNotFoundError:
            return None
        if stat.st_size != metadata.size_bytes:
            return None
        return metadata

    def delete_object(self, storage_key: str) -> None:
        for path in (self._object_path(storage_key), self._meta_path(storage_key)):
            try:
                os.remove(path)
            except FileNotFoundError:
                continue

    def _object_path(self, storage_key: str) -> str:
        return os.path.join(self.root, storage_key)

    def _meta_path(self, storage_key: str) -> str:
        return f"{self._object_path(storage_key)}{META_SUFFIX}"

    def _read_metadata(self, storage_key: str) -> ObjectMetadata | None:
        try:
            with open(self._meta_path(storage_key), encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError):
            return None
        if not isinstance(payload, Mapping):
            return None
        try:
            size_bytes = int(payload["size_bytes"])
            content_type = str(payload["content_type"])
        except (KeyError, TypeError, ValueError):
            return None
        return ObjectMetadata(size_bytes=size_bytes, content_type=content_type)

    def _sign(
        self,
        media: MediaFile,
        *,
        op: str,
        method: str,
        salt: str,
        ttl: int,
    ) -> tuple[str, datetime]:
        token = signing.dumps(
            {"op": op, "media": media.pk, "method": method}, salt=salt
        )
        return token, timezone.now() + timedelta(seconds=ttl)

    def _capability_url(self, base_url: str, path: str, token: str) -> str:
        return f"{base_url.rstrip('/')}{path.format(token=token)}"


def _load_s3_sdk():
    """Import the optional S3 SDK lazily and return ``(boto3, Config, ClientError)``.

    ``boto3`` ships in the optional ``storage-s3`` dependency group, so it is
    imported on first use rather than at module import time; its absence is a
    configuration error naming that extra.
    """

    try:
        import boto3
        from botocore.config import Config
        from botocore.exceptions import ClientError
    except ImportError as exc:
        raise ImproperlyConfigured(S3_EXTRA_MESSAGE) from exc
    return boto3, Config, ClientError


class S3StorageAdapter:
    """Any S3-compatible object storage (MinIO, AWS S3, another S3 API).

    Uploads and reads use presigned URLs, so the backend never proxies bytes and
    there is no controlled-upload endpoint for this backend.
    """

    supports_controlled_upload = False

    def __init__(
        self,
        *,
        endpoint_url: str,
        bucket: str,
        region: str,
        access_key: str,
        secret_key: str,
        addressing_style: str,
    ) -> None:
        self.endpoint_url = endpoint_url
        self.bucket = bucket
        self.region = region
        self.access_key = access_key
        self.secret_key = secret_key
        self.addressing_style = addressing_style

    def create_upload_url(self, *, media: MediaFile, base_url: str) -> SignedUrl:
        url = self._client().generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self.bucket,
                "Key": media.storage_key,
                "ContentType": media.mime_type,
                # The signature is bound to the declared size, so the provider
                # rejects a body that does not match the metadata row.
                "ContentLength": media.size_bytes,
            },
            ExpiresIn=settings.MEDIA_UPLOAD_URL_TTL,
        )
        return SignedUrl(
            url=url,
            method=UPLOAD_METHOD,
            expires_at=timezone.now()
            + timedelta(seconds=settings.MEDIA_UPLOAD_URL_TTL),
        )

    def create_access_url(self, *, media: MediaFile, base_url: str) -> SignedUrl:
        url = self._client().generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": media.storage_key},
            ExpiresIn=settings.MEDIA_ACCESS_URL_TTL,
        )
        return SignedUrl(
            url=url,
            method=DOWNLOAD_METHOD,
            expires_at=timezone.now()
            + timedelta(seconds=settings.MEDIA_ACCESS_URL_TTL),
        )

    def verify_object(self, storage_key: str) -> ObjectMetadata | None:
        """Return ``head_object`` metadata, or ``None`` for a missing object."""

        _, _, ClientError = _load_s3_sdk()
        try:
            head = self._client().head_object(Bucket=self.bucket, Key=storage_key)
        except ClientError as exc:
            if not _is_missing_object(exc):
                raise
            return None
        return ObjectMetadata(
            size_bytes=int(head["ContentLength"]),
            content_type=head.get("ContentType") or "",
        )

    def delete_object(self, storage_key: str) -> None:
        self._client().delete_object(Bucket=self.bucket, Key=storage_key)

    def _client(self):
        boto3, Config, _ = _load_s3_sdk()
        return boto3.client(
            "s3",
            endpoint_url=self.endpoint_url or None,
            region_name=self.region,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            config=Config(s3={"addressing_style": self.addressing_style}),
        )


def _is_missing_object(exc: Exception) -> bool:
    response = getattr(exc, "response", None) or {}
    status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    code = str(response.get("Error", {}).get("Code", ""))
    return status == 404 or code in {"404", "NoSuchKey", "NotFound"}


@lru_cache(maxsize=1)
def get_storage_adapter() -> StorageAdapter:
    """Return the adapter for ``MEDIA_STORAGE_BACKEND`` (cached per process).

    Tests that change the media storage settings must reset the cache with
    ``get_storage_adapter.cache_clear()``.
    """

    backend = settings.MEDIA_STORAGE_BACKEND
    if backend == "local":
        return LocalStorageAdapter(settings.MEDIA_STORAGE_ROOT)
    if backend == "s3":
        return S3StorageAdapter(
            endpoint_url=settings.MEDIA_S3_ENDPOINT_URL,
            bucket=settings.MEDIA_S3_BUCKET,
            region=settings.MEDIA_S3_REGION,
            access_key=settings.MEDIA_S3_ACCESS_KEY,
            secret_key=settings.MEDIA_S3_SECRET_KEY,
            addressing_style=settings.MEDIA_S3_ADDRESSING_STYLE,
        )
    raise ImproperlyConfigured(
        f"Unknown MEDIA_STORAGE_BACKEND: {backend!r}. Use 'local' or 's3'."
    )
