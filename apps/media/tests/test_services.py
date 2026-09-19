from __future__ import annotations

import hashlib
import logging
from datetime import timedelta

import pytest
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone

from apps.common.exceptions import APIError
from apps.media import services
from apps.media.models import MediaFile
from apps.media.storage import get_storage_adapter

PUBLIC = MediaFile.Visibility.PUBLIC
PROTECTED = MediaFile.Visibility.PROTECTED
BASE_URL = "http://testserver"


def _token_from_url(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1]


def _upload_token(media: MediaFile) -> str:
    signed = services.issue_upload_url(media, base_url=BASE_URL)
    return _token_from_url(signed.url)


# ---------------------------------------------------------------------------
# Metadata creation: allow-list, size limit and the opaque object key.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("mime_type", ["text/html", "application/pdf", "", "image/svg"])
def test_create_media_file_rejects_a_mime_outside_the_allow_list(mime_type):
    with pytest.raises(APIError) as excinfo:
        services.create_media_file(mime_type=mime_type, size_bytes=2048)

    assert (excinfo.value.status_code, excinfo.value.default_code) == (
        422,
        "MEDIA_INVALID",
    )
    assert "mime_type" in excinfo.value.fields
    assert not MediaFile.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize("size_bytes", [0, -1])
def test_create_media_file_rejects_a_non_positive_size(size_bytes):
    with pytest.raises(APIError) as excinfo:
        services.create_media_file(mime_type="image/png", size_bytes=size_bytes)

    assert (excinfo.value.status_code, excinfo.value.default_code) == (
        422,
        "MEDIA_INVALID",
    )
    assert "size_bytes" in excinfo.value.fields
    assert not MediaFile.objects.exists()


@pytest.mark.django_db
def test_create_media_file_rejects_a_size_above_the_configured_limit(settings):
    settings.MEDIA_MAX_UPLOAD_BYTES = 16
    services.create_media_file(mime_type="image/png", size_bytes=16)

    with pytest.raises(APIError) as excinfo:
        services.create_media_file(mime_type="image/png", size_bytes=17)

    assert (excinfo.value.status_code, excinfo.value.default_code) == (
        422,
        "MEDIA_INVALID",
    )
    assert "size_bytes" in excinfo.value.fields
    assert MediaFile.objects.count() == 1


@pytest.mark.django_db
def test_create_media_file_mints_an_opaque_server_side_key():
    media = services.create_media_file(
        original_name="../../etc/passwd.png",
        mime_type="image/png",
        size_bytes=2048,
    )

    assert media.storage_key.startswith("media/")
    assert media.storage_key.endswith(".png")
    assert "passwd" not in media.storage_key
    assert ".." not in media.storage_key
    assert len(media.storage_key) == len("media/") + 32 + len(".png")
    assert media.visibility == PROTECTED
    assert media.original_name == "../../etc/passwd.png"

    second = services.create_media_file(mime_type="image/png", size_bytes=2048)
    assert second.storage_key != media.storage_key


@pytest.mark.django_db
def test_create_media_file_keeps_the_declared_visibility_and_checksum():
    media = services.create_media_file(
        mime_type="image/webp",
        size_bytes=8,
        checksum="sha256:abc",
        visibility=PUBLIC,
    )

    assert media.visibility == PUBLIC
    assert media.checksum == "sha256:abc"
    assert media.mime_type == "image/webp"


@pytest.mark.django_db
def test_get_media_file_returns_the_row_or_none(media_file):
    media = media_file()

    assert services.get_media_file(media.pk) == media
    assert services.get_media_file(media.pk + 1000) is None


# ---------------------------------------------------------------------------
# URL issuance: upload contract, access decision before storage, verification.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_issue_upload_url_returns_an_absolute_contract_with_the_configured_ttl(
    media_file,
):
    media = media_file()

    signed = services.issue_upload_url(media, base_url=BASE_URL)

    assert signed.method == "PUT"
    assert signed.url.startswith(f"{BASE_URL}/api/v1/media/upload/")
    assert media.storage_key not in signed.url
    remaining = signed.expires_at - timezone.now()
    assert (
        timedelta(seconds=settings.MEDIA_UPLOAD_URL_TTL - 5)
        <= remaining
        <= timedelta(seconds=settings.MEDIA_UPLOAD_URL_TTL + 5)
    )


@pytest.mark.django_db
def test_issue_access_url_signs_public_media_for_an_anonymous_actor(stored_media):
    media, _ = stored_media(visibility=PUBLIC)

    signed = services.issue_access_url(media, actor=AnonymousUser(), base_url=BASE_URL)

    assert signed.method == "GET"
    assert signed.url.startswith(f"{BASE_URL}/api/v1/media/file/")
    assert media.storage_key not in signed.url
    remaining = signed.expires_at - timezone.now()
    assert (
        timedelta(seconds=settings.MEDIA_ACCESS_URL_TTL - 5)
        <= remaining
        <= timedelta(seconds=settings.MEDIA_ACCESS_URL_TTL + 5)
    )


@pytest.mark.django_db
def test_protected_access_is_decided_before_any_storage_call(media_file, monkeypatch):
    media = media_file(visibility=PROTECTED)

    def _unreachable_storage():
        raise AssertionError("storage must not be reached before the access decision")

    monkeypatch.setattr(services, "get_storage_adapter", _unreachable_storage)

    with pytest.raises(APIError) as excinfo:
        services.issue_access_url(media, actor=AnonymousUser(), base_url=BASE_URL)

    assert (excinfo.value.status_code, excinfo.value.default_code) == (
        401,
        "AUTHENTICATION_REQUIRED",
    )


@pytest.mark.django_db
def test_protected_access_is_denied_for_an_authenticated_actor_without_access(
    stored_media,
    media_reference,
    make_user,
):
    media, _ = stored_media(visibility=PROTECTED)
    media_reference(media, access_level="paid")

    with pytest.raises(APIError) as excinfo:
        services.issue_access_url(
            media,
            actor=make_user(username="no-entitlement"),
            base_url=BASE_URL,
        )

    assert (excinfo.value.status_code, excinfo.value.default_code) == (
        403,
        "MEDIA_ACCESS_DENIED",
    )


@pytest.mark.django_db
def test_protected_access_is_signed_for_an_anonymous_preview_reference(
    stored_media,
    media_reference,
):
    media, _ = stored_media(visibility=PROTECTED)
    media_reference(media, access_level="free", is_demo_preview=True)

    signed = services.issue_access_url(media, actor=AnonymousUser(), base_url=BASE_URL)

    assert signed.url.startswith(f"{BASE_URL}/api/v1/media/file/")


@pytest.mark.django_db
def test_protected_access_is_signed_for_an_authenticated_actor_with_access(
    stored_media,
    media_reference,
    make_user,
):
    media, _ = stored_media(visibility=PROTECTED)
    media_reference(media, access_level="free")

    signed = services.issue_access_url(
        media,
        actor=make_user(username="reader-with-access"),
        base_url=BASE_URL,
    )

    assert signed.url.startswith(f"{BASE_URL}/api/v1/media/file/")


@pytest.mark.django_db
def test_access_url_is_422_when_the_object_is_missing(media_file):
    media = media_file(visibility=PUBLIC)

    with pytest.raises(APIError) as excinfo:
        services.issue_access_url(media, actor=AnonymousUser(), base_url=BASE_URL)

    assert (excinfo.value.status_code, excinfo.value.default_code) == (
        422,
        "MEDIA_INVALID",
    )


@pytest.mark.django_db
def test_access_url_is_422_when_the_stored_object_size_differs(stored_media):
    media, _ = stored_media(visibility=PUBLIC)
    MediaFile.objects.filter(pk=media.pk).update(size_bytes=media.size_bytes + 1)
    media.refresh_from_db()

    with pytest.raises(APIError) as excinfo:
        services.issue_access_url(media, actor=AnonymousUser(), base_url=BASE_URL)

    assert (excinfo.value.status_code, excinfo.value.default_code) == (
        422,
        "MEDIA_INVALID",
    )


@pytest.mark.django_db
def test_protected_access_fails_closed_without_an_access_provider(media_file, settings):
    settings.MEDIA_ACCESS_POLICY_PROVIDER = ""
    media = media_file(visibility=PROTECTED)

    with pytest.raises(APIError) as excinfo:
        services.issue_access_url(media, actor=AnonymousUser(), base_url=BASE_URL)

    assert (excinfo.value.status_code, excinfo.value.default_code) == (
        403,
        "MEDIA_ACCESS_DENIED",
    )


@pytest.mark.django_db
def test_protected_access_fails_closed_for_an_unresolvable_provider(
    media_file,
    settings,
):
    settings.MEDIA_ACCESS_POLICY_PROVIDER = "apps.media.storage.missing_provider"
    media = media_file(visibility=PROTECTED)

    with pytest.raises(APIError) as excinfo:
        services.issue_access_url(media, actor=AnonymousUser(), base_url=BASE_URL)

    assert (excinfo.value.status_code, excinfo.value.default_code) == (
        403,
        "MEDIA_ACCESS_DENIED",
    )


# ---------------------------------------------------------------------------
# Deletion: the content-owned guard, the detach path and storage cleanup.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_delete_media_file_detaches_an_unpublished_reference(
    media_file,
    media_reference,
):
    media = media_file()
    block = media_reference(media, block_status="draft")

    services.delete_media_file(media)

    assert not MediaFile.objects.filter(pk=media.pk).exists()
    block.refresh_from_db()
    assert block.media_id is None


@pytest.mark.django_db
def test_delete_media_file_refuses_a_published_reference(
    media_file,
    media_reference,
):
    media = media_file()
    media_reference(media)

    with pytest.raises(APIError) as excinfo:
        services.delete_media_file(media)

    assert (excinfo.value.status_code, excinfo.value.default_code) == (
        409,
        "CONTENT_CONFLICT",
    )
    assert MediaFile.objects.filter(pk=media.pk).exists()


@pytest.mark.django_db
def test_delete_media_file_allows_a_reference_that_is_not_published(
    media_file,
    media_reference,
):
    media = media_file()
    media_reference(media, block_status="reviewed")

    services.delete_media_file(media)

    assert not MediaFile.objects.filter(pk=media.pk).exists()


@pytest.mark.django_db
def test_delete_media_file_is_404_for_a_row_that_vanished_before_the_lock(
    media_file,
):
    """A duplicate DELETE whose row vanished before the lock answers 404.

    The repeated request passed the read of the view while the first one was
    still deleting, so the row is only discovered to be gone under the lock.
    """

    media = media_file()
    services.delete_media_file(media)

    with pytest.raises(APIError) as excinfo:
        services.delete_media_file(media)

    assert (excinfo.value.status_code, excinfo.value.default_code) == (
        404,
        "RESOURCE_NOT_FOUND",
    )
    assert not MediaFile.objects.filter(pk=media.pk).exists()


@pytest.mark.django_db
def test_delete_media_file_fails_closed_without_a_guard_provider(media_file, settings):
    settings.MEDIA_DELETE_GUARD_PROVIDER = ""
    media = media_file()

    with pytest.raises(APIError) as excinfo:
        services.delete_media_file(media)

    assert (excinfo.value.status_code, excinfo.value.default_code) == (
        409,
        "CONTENT_CONFLICT",
    )
    assert MediaFile.objects.filter(pk=media.pk).exists()


@pytest.mark.django_db
def test_delete_media_file_fails_closed_for_an_unresolvable_guard_provider(
    media_file,
    settings,
):
    settings.MEDIA_DELETE_GUARD_PROVIDER = "apps.media.storage.missing_guard"
    media = media_file()

    with pytest.raises(APIError) as excinfo:
        services.delete_media_file(media)

    assert (excinfo.value.status_code, excinfo.value.default_code) == (
        409,
        "CONTENT_CONFLICT",
    )
    assert MediaFile.objects.filter(pk=media.pk).exists()


@pytest.mark.django_db
def test_delete_media_file_cleans_storage_on_commit(
    stored_media,
    django_capture_on_commit_callbacks,
):
    media, _ = stored_media(visibility=PUBLIC)
    adapter = get_storage_adapter()
    assert adapter.verify_object(media.storage_key) is not None

    with django_capture_on_commit_callbacks(execute=True):
        services.delete_media_file(media)

    assert not MediaFile.objects.filter(pk=media.pk).exists()
    assert adapter.verify_object(media.storage_key) is None


@pytest.mark.django_db
def test_storage_cleanup_failure_is_logged_and_never_rolls_back(
    media_file,
    django_capture_on_commit_callbacks,
    monkeypatch,
    caplog,
):
    media = media_file()

    class _FailingAdapter:
        def delete_object(self, storage_key: str) -> None:
            raise RuntimeError("provider unavailable")

    monkeypatch.setattr(services, "get_storage_adapter", _FailingAdapter)

    with (
        caplog.at_level(logging.WARNING, logger="apps.media.services"),
        django_capture_on_commit_callbacks(execute=True),
    ):
        services.delete_media_file(media)

    assert not MediaFile.objects.filter(pk=media.pk).exists()
    messages = [record.getMessage() for record in caplog.records]
    assert any(str(media.pk) in message for message in messages)
    assert all(media.storage_key not in message for message in messages)


# ---------------------------------------------------------------------------
# Controlled upload and download.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_accept_controlled_upload_stores_matching_bytes(media_file):
    media = media_file(size_bytes=2048)
    payload = b"x" * 2048

    returned = services.accept_controlled_upload(_upload_token(media), payload)

    assert returned.pk == media.pk
    with get_storage_adapter().read_object(media.storage_key) as content:
        assert content.read() == payload


@pytest.mark.django_db
def test_accept_controlled_upload_rejects_a_size_mismatch_and_stores_nothing(
    media_file,
):
    media = media_file(size_bytes=2048)

    with pytest.raises(APIError) as excinfo:
        services.accept_controlled_upload(_upload_token(media), b"x" * 2047)

    assert (excinfo.value.status_code, excinfo.value.default_code) == (
        422,
        "MEDIA_INVALID",
    )
    assert get_storage_adapter().verify_object(media.storage_key) is None


@pytest.mark.django_db
def test_accept_controlled_upload_verifies_a_declared_sha256(media_file):
    payload = b"x" * 16
    digest = hashlib.sha256(payload).hexdigest()

    for checksum in (f"sha256:{digest}", digest.upper()):
        media = media_file(size_bytes=len(payload), checksum=checksum)

        services.accept_controlled_upload(_upload_token(media), payload)

        assert get_storage_adapter().verify_object(media.storage_key) is not None


@pytest.mark.django_db
def test_accept_controlled_upload_rejects_a_checksum_mismatch_and_stores_nothing(
    media_file,
):
    payload = b"x" * 16
    media = media_file(size_bytes=len(payload), checksum="sha256:" + "0" * 64)

    with pytest.raises(APIError) as excinfo:
        services.accept_controlled_upload(_upload_token(media), payload)

    assert (excinfo.value.status_code, excinfo.value.default_code) == (
        422,
        "MEDIA_INVALID",
    )
    assert get_storage_adapter().verify_object(media.storage_key) is None


@pytest.mark.django_db
def test_accept_controlled_upload_rejects_garbage_and_expired_tokens(
    media_file,
    settings,
):
    media = media_file(size_bytes=4)
    token = _upload_token(media)

    with pytest.raises(APIError) as garbage:
        services.accept_controlled_upload("not-a-token", b"abcd")
    assert (garbage.value.status_code, garbage.value.default_code) == (
        401,
        "AUTHENTICATION_REQUIRED",
    )

    settings.MEDIA_UPLOAD_URL_TTL = -1
    with pytest.raises(APIError) as expired:
        services.accept_controlled_upload(token, b"abcd")
    assert (expired.value.status_code, expired.value.default_code) == (
        401,
        "AUTHENTICATION_REQUIRED",
    )
    assert get_storage_adapter().verify_object(media.storage_key) is None


@pytest.mark.django_db
def test_accept_controlled_upload_rejects_a_token_of_another_operation(stored_media):
    media, _ = stored_media(visibility=PUBLIC)
    signed = services.issue_access_url(media, actor=AnonymousUser(), base_url=BASE_URL)

    with pytest.raises(APIError) as excinfo:
        services.accept_controlled_upload(_token_from_url(signed.url), b"x")

    assert (excinfo.value.status_code, excinfo.value.default_code) == (
        401,
        "AUTHENTICATION_REQUIRED",
    )


@pytest.mark.django_db
def test_accept_controlled_upload_is_404_without_a_controlled_backend(
    media_file,
    monkeypatch,
):
    media = media_file(size_bytes=4)
    token = _upload_token(media)

    class _PresignOnlyAdapter:
        supports_controlled_upload = False

    monkeypatch.setattr(services, "get_storage_adapter", _PresignOnlyAdapter)

    with pytest.raises(APIError) as excinfo:
        services.accept_controlled_upload(token, b"abcd")

    assert (excinfo.value.status_code, excinfo.value.default_code) == (
        404,
        "RESOURCE_NOT_FOUND",
    )


@pytest.mark.django_db
def test_accept_controlled_upload_is_404_when_the_media_row_is_gone(media_file):
    media = media_file(size_bytes=4)
    token = _upload_token(media)
    MediaFile.objects.filter(pk=media.pk).delete()

    with pytest.raises(APIError) as excinfo:
        services.accept_controlled_upload(token, b"abcd")

    assert (excinfo.value.status_code, excinfo.value.default_code) == (
        404,
        "RESOURCE_NOT_FOUND",
    )


@pytest.mark.django_db
def test_open_controlled_download_returns_the_stored_bytes(stored_media):
    media, payload = stored_media(visibility=PUBLIC)
    signed = services.issue_access_url(media, actor=AnonymousUser(), base_url=BASE_URL)

    returned, content = services.open_controlled_download(_token_from_url(signed.url))

    try:
        assert returned.pk == media.pk
        assert content.read() == payload
    finally:
        content.close()


@pytest.mark.django_db
def test_open_controlled_download_is_404_for_a_missing_object(media_file):
    media = media_file(size_bytes=4)
    signed = get_storage_adapter().create_access_url(
        media=media,
        base_url=BASE_URL,
    )

    with pytest.raises(APIError) as excinfo:
        services.open_controlled_download(_token_from_url(signed.url))

    assert (excinfo.value.status_code, excinfo.value.default_code) == (
        404,
        "RESOURCE_NOT_FOUND",
    )


@pytest.mark.django_db
def test_open_controlled_download_rejects_a_garbage_token(media_file):
    with pytest.raises(APIError) as excinfo:
        services.open_controlled_download("not-a-token")

    assert (excinfo.value.status_code, excinfo.value.default_code) == (
        401,
        "AUTHENTICATION_REQUIRED",
    )


@pytest.mark.django_db
def test_open_controlled_download_is_404_without_a_controlled_backend(
    stored_media,
    monkeypatch,
):
    media, _ = stored_media(visibility=PUBLIC)
    signed = services.issue_access_url(media, actor=AnonymousUser(), base_url=BASE_URL)

    class _PresignOnlyAdapter:
        supports_controlled_upload = False

    monkeypatch.setattr(services, "get_storage_adapter", _PresignOnlyAdapter)

    with pytest.raises(APIError) as excinfo:
        services.open_controlled_download(_token_from_url(signed.url))

    assert (excinfo.value.status_code, excinfo.value.default_code) == (
        404,
        "RESOURCE_NOT_FOUND",
    )
