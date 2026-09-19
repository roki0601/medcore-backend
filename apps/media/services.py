from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, BinaryIO
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils.module_loading import import_string

from apps.common.exceptions import APIError
from apps.media.models import MediaFile
from apps.media.storage import (
    DOWNLOAD_METHOD,
    DOWNLOAD_OPERATION,
    UPLOAD_METHOD,
    UPLOAD_OPERATION,
    ObjectMetadata,
    SignedUrl,
    decode_token,
    get_storage_adapter,
)

logger = logging.getLogger(__name__)

#: Object suffix per allow-listed MIME type. A deployment that widens
#: ``MEDIA_ALLOWED_MIME_TYPES`` still gets an opaque key, just without a suffix.
MIME_SUFFIXES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


@dataclass(frozen=True)
class MediaAccessDecision:
    """Outcome of the content-owned decision about one media row.

    The access provider named by ``MEDIA_ACCESS_POLICY_PROVIDER`` returns this
    shape (the content-owned ``MediaAccessDecision``). The media app never
    imports the content app, so the fields are mirrored here and the fail-closed
    default is expressed with the same value object.
    """

    allowed: bool
    requires_authentication: bool


#: Fail-closed result used when the access provider is missing or unresolvable.
_DENIED_ACCESS = MediaAccessDecision(allowed=False, requires_authentication=False)


def _invalid_media(detail: str, fields: dict[str, Any] | None = None) -> APIError:
    return APIError(
        detail,
        code="MEDIA_INVALID",
        status_code=422,
        fields=fields,
    )


def _not_found() -> APIError:
    return APIError("Resource not found.", code="RESOURCE_NOT_FOUND", status_code=404)


def _validation_error(exc: DjangoValidationError) -> APIError:
    fields = getattr(exc, "message_dict", None) or {"non_field_errors": exc.messages}
    return APIError(
        "Request validation failed.",
        code="VALIDATION_ERROR",
        status_code=422,
        fields=fields,
    )


def _load_provider(path: str) -> Callable:
    """Resolve a content-owned policy provider declared in the settings.

    The two decisions ``apps.media`` needs belong to ``content``: whether an
    actor may read the bytes behind a media row, and whether a media row may be
    deleted. They arrive as importable paths so ``apps.media`` keeps no static
    import of the content app. An empty or unresolvable path is a configuration
    error the callers translate into their fail-closed answer.
    """

    if not path:
        raise ImproperlyConfigured("No media policy provider is configured.")
    try:
        provider = import_string(path)
    except (ImportError, AttributeError) as exc:
        raise ImproperlyConfigured(
            f"Media policy provider {path!r} cannot be imported."
        ) from exc
    if not callable(provider):
        raise ImproperlyConfigured(f"Media policy provider {path!r} is not callable.")
    return provider


def _load_delete_guard() -> Callable:
    """Return the content-owned deletion guard, refusing deletion when unset."""

    try:
        return _load_provider(settings.MEDIA_DELETE_GUARD_PROVIDER)
    except ImproperlyConfigured as exc:
        raise APIError(
            "Media deletion is unavailable.",
            code="CONTENT_CONFLICT",
            status_code=409,
        ) from exc


def _load_access_policy() -> Callable | None:
    """Return the content-owned access decision, or ``None`` when unset."""

    try:
        return _load_provider(settings.MEDIA_ACCESS_POLICY_PROVIDER)
    except ImproperlyConfigured:
        logger.warning(
            "MEDIA_ACCESS_POLICY_PROVIDER is not configured; denying protected "
            "media access."
        )
        return None


def _generate_storage_key(mime_type: str) -> str:
    """Mint an opaque object key; no client input ever reaches it."""

    return f"media/{uuid4().hex}{MIME_SUFFIXES.get(mime_type, '')}"


def create_media_file(
    *,
    original_name: str = "",
    mime_type: str,
    size_bytes: int,
    checksum: str = "",
    visibility: str = MediaFile.Visibility.PROTECTED,
) -> MediaFile:
    """Create the metadata row for one upload; the binary is stored later.

    The declared MIME type must be allow-listed and the declared size must be
    positive and within ``MEDIA_MAX_UPLOAD_BYTES``; the object key is generated
    here and never derived from client input.
    """

    fields: dict[str, list[str]] = {}
    if mime_type not in settings.MEDIA_ALLOWED_MIME_TYPES:
        allowed = ", ".join(settings.MEDIA_ALLOWED_MIME_TYPES)
        fields["mime_type"] = [f"Unsupported MIME type. Allowed types: {allowed}."]
    if (
        not isinstance(size_bytes, int)
        or isinstance(size_bytes, bool)
        or not 0 < size_bytes <= settings.MEDIA_MAX_UPLOAD_BYTES
    ):
        fields["size_bytes"] = [
            f"Ensure this value is between 1 and {settings.MEDIA_MAX_UPLOAD_BYTES}."
        ]
    if fields:
        raise _invalid_media("Media metadata is invalid.", fields)

    media = MediaFile(
        storage_key=_generate_storage_key(mime_type),
        original_name=original_name,
        mime_type=mime_type,
        size_bytes=size_bytes,
        checksum=checksum,
        visibility=visibility,
    )
    try:
        media.full_clean()
    except DjangoValidationError as exc:
        raise _validation_error(exc) from exc
    media.save()
    return media


def get_media_file(media_id: int) -> MediaFile | None:
    """Read one media row by its numeric id."""

    return MediaFile.objects.filter(pk=media_id).first()


def delete_media_file(media: MediaFile) -> None:
    """Delete one media row, refusing while published content references it.

    The row is locked first and the content-owned guard runs inside the same
    transaction; the guard locks the published referencing blocks, so a
    reference that was committed by a concurrent publish is seen and refused
    instead of being detached. Storage cleanup is registered with
    ``transaction.on_commit``: a provider failure is logged and never rolls back
    the committed database delete.
    """

    with transaction.atomic():
        try:
            locked = MediaFile.objects.select_for_update().get(pk=media.pk)
        except MediaFile.DoesNotExist as exc:
            # A repeated DELETE whose row vanished between the read of the view
            # and this lock is the documented 404, not a server error.
            raise _not_found() from exc
        _load_delete_guard()(locked)
        media_id = locked.pk
        storage_key = locked.storage_key
        locked.delete()
        transaction.on_commit(lambda: _delete_object_safely(media_id, storage_key))


def _delete_object_safely(media_id: int, storage_key: str) -> None:
    """Best-effort object cleanup after the row is committed as deleted."""

    try:
        get_storage_adapter().delete_object(storage_key)
    except Exception:
        logger.warning(
            "Media object cleanup failed for media %s.",
            media_id,
            exc_info=True,
        )


def issue_upload_url(media: MediaFile, *, base_url: str) -> SignedUrl:
    """Issue the upload contract of the selected storage backend.

    A stored object is never overwritten: a second upload contract for it would
    let the client replace already verified bytes behind the same key, so the
    request is refused with 409 ``CONTENT_CONFLICT``. The local backend refuses
    the overwrite at write time; this refusal closes the same hole for the
    S3-compatible backend, which would accept the presigned ``PUT``.
    """

    adapter = get_storage_adapter()
    if adapter.verify_object(media.storage_key) is not None:
        raise APIError(
            "This media object is already uploaded.",
            code="CONTENT_CONFLICT",
            status_code=409,
        )
    return adapter.create_upload_url(media=media, base_url=base_url)


def issue_access_url(media: MediaFile, *, actor, base_url: str) -> SignedUrl:
    """Issue a short-lived read URL after the access decision and verification.

    Authorization always runs before any storage call, so the endpoint is not an
    object-existence oracle; the object metadata is verified before the URL is
    signed. Public media carries no access restriction and is signed for every
    actor.
    """

    if media.visibility != MediaFile.Visibility.PUBLIC:
        decision = _decide_protected_access(media, actor)
        if decision.requires_authentication:
            raise APIError(
                "Authentication is required to read this media.",
                code="AUTHENTICATION_REQUIRED",
                status_code=401,
            )
        if not decision.allowed:
            raise APIError(
                "Media access is denied.",
                code="MEDIA_ACCESS_DENIED",
                status_code=403,
            )
    _verify_or_fail(media)
    return get_storage_adapter().create_access_url(media=media, base_url=base_url)


def _decide_protected_access(media: MediaFile, actor) -> MediaAccessDecision:
    """Ask the content-owned policy, denying access when it cannot be resolved."""

    policy = _load_access_policy()
    if policy is None:
        return _DENIED_ACCESS
    decision = policy(media, actor)
    return MediaAccessDecision(
        allowed=bool(decision.allowed),
        requires_authentication=bool(decision.requires_authentication),
    )


def _verify_or_fail(media: MediaFile) -> ObjectMetadata:
    """Confirm the stored object exists and matches the declared size."""

    metadata = get_storage_adapter().verify_object(media.storage_key)
    if metadata is None or metadata.size_bytes != media.size_bytes:
        raise _invalid_media("Media object is not available.")
    return metadata


def _checksum_matches(checksum: str, data: bytes) -> bool:
    """Compare a declared ``sha256:<hex>`` or bare hex digest with the bytes."""

    algorithm, separator, digest = checksum.partition(":")
    if not separator:
        algorithm, digest = "sha256", checksum
    expected = digest.strip().lower()
    if algorithm.strip().lower() != "sha256" or not expected:
        return False
    return hashlib.sha256(data).hexdigest() == expected


def validate_upload_token(token: str) -> MediaFile:
    """Validate one upload capability token and return its media row.

    The token is the credential of the controlled upload: it is bound to the
    upload operation, one media row, the ``PUT`` method and its expiry. The
    receiver view calls this before it reads the request body, so a garbage or
    oversized request is refused without being buffered.
    """

    payload = decode_token(
        token,
        salt=settings.MEDIA_UPLOAD_TOKEN_SALT,
        expected_op=UPLOAD_OPERATION,
        expected_method=UPLOAD_METHOD,
        max_age=settings.MEDIA_UPLOAD_URL_TTL,
    )
    adapter = get_storage_adapter()
    if not getattr(adapter, "supports_controlled_upload", False):
        raise _not_found()

    media = get_media_file(payload["media"])
    if media is None:
        raise _not_found()
    return media


def accept_controlled_upload(token: str, data: bytes) -> MediaFile:
    """Store the bytes of one capability-token upload after verifying them.

    The declared size (and the checksum when the row carries one) must match
    before anything is written.
    """

    media = validate_upload_token(token)
    if len(data) != media.size_bytes:
        raise _invalid_media(
            "Uploaded size does not match the declared metadata.",
            {
                "size_bytes": [
                    f"Expected {media.size_bytes} bytes, received {len(data)}."
                ]
            },
        )
    if media.checksum and not _checksum_matches(media.checksum, data):
        raise _invalid_media(
            "Uploaded checksum does not match the declared metadata.",
            {"checksum": ["Checksum mismatch."]},
        )

    get_storage_adapter().write_object(media.storage_key, data, media.mime_type)
    return media


def open_controlled_download(token: str) -> tuple[MediaFile, BinaryIO]:
    """Open the stored object of one capability-token download.

    Returns the media row and an open binary handle; the caller closes it. A
    missing row, a missing object or a backend without the controlled download
    contract is 404 ``RESOURCE_NOT_FOUND``.
    """

    payload = decode_token(
        token,
        salt=settings.MEDIA_ACCESS_TOKEN_SALT,
        expected_op=DOWNLOAD_OPERATION,
        expected_method=DOWNLOAD_METHOD,
        max_age=settings.MEDIA_ACCESS_URL_TTL,
    )
    adapter = get_storage_adapter()
    reader = getattr(adapter, "read_object", None)
    if not callable(reader):
        raise _not_found()

    media = get_media_file(payload["media"])
    if media is None:
        raise _not_found()

    try:
        content = reader(media.storage_key)
    except OSError as exc:
        raise _not_found() from exc
    return media, content
