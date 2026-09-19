from __future__ import annotations

import json

import pytest

from apps.media.models import MediaFile
from apps.media.storage import get_storage_adapter

MEDIA_URL = "/api/v1/media/"
PUBLIC = MediaFile.Visibility.PUBLIC
PROTECTED = MediaFile.Visibility.PROTECTED
PNG_PAYLOAD = b"\x89PNG" + b"0" * 2044


def _create_media(client, **payload) -> dict:
    body = {
        "original_name": "structure.png",
        "mime_type": "image/png",
        "size_bytes": len(PNG_PAYLOAD),
        "visibility": PUBLIC,
    }
    body.update(payload)
    response = client.post(MEDIA_URL, body, format="json")
    assert response.status_code == 201, response.content
    return response.json()


def _bytes_of(response) -> bytes:
    return b"".join(response.streaming_content)


# ---------------------------------------------------------------------------
# The upload round trip over HTTP.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_upload_round_trip_serves_the_stored_bytes(integration_client, api_client):
    media = _create_media(integration_client)

    upload = integration_client.get(f"{MEDIA_URL}{media['id']}/upload-url/")
    assert upload.status_code == 200
    contract = upload.json()
    assert contract["method"] == "PUT"
    assert contract["upload_url"].startswith("http://testserver/api/v1/media/upload/")

    stored = api_client.put(
        contract["upload_url"],
        data=PNG_PAYLOAD,
        content_type="application/octet-stream",
    )
    assert stored.status_code == 204
    assert stored.content == b""

    access = api_client.get(f"{MEDIA_URL}{media['id']}/access-url/")
    assert access.status_code == 200
    signed = access.json()
    assert signed["method"] == "GET"
    assert signed["access_url"].startswith("http://testserver/api/v1/media/file/")

    downloaded = api_client.get(signed["access_url"])
    assert downloaded.status_code == 200
    assert downloaded["Content-Type"] == "image/png"
    assert downloaded["Content-Disposition"] == 'inline; filename="structure.png"'
    assert _bytes_of(downloaded) == PNG_PAYLOAD


@pytest.mark.django_db
def test_a_body_above_the_configured_limit_is_422_before_it_is_buffered(
    integration_client,
    api_client,
    settings,
):
    """The media limit answers inside the envelope, not as Django's 400.

    Both the media limit and Django's body limit are set to the same value, as
    the settings derive them, so the request would otherwise die with
    ``RequestDataTooBig`` (400, HTML) before the view could answer.
    """

    settings.MEDIA_MAX_UPLOAD_BYTES = 1024
    settings.DATA_UPLOAD_MAX_MEMORY_SIZE = 1024
    media = _create_media(integration_client, size_bytes=1024)
    contract = integration_client.get(f"{MEDIA_URL}{media['id']}/upload-url/").json()

    response = api_client.put(
        contract["upload_url"],
        data=b"x" * 1025,
        content_type="application/octet-stream",
    )

    assert response.status_code == 422
    assert response.json()["code"] == "MEDIA_INVALID"
    assert response.json()["fields"]["size_bytes"]
    row = MediaFile.objects.get(pk=media["id"])
    assert get_storage_adapter().verify_object(row.storage_key) is None


@pytest.mark.django_db
def test_the_receiver_checks_the_token_before_it_reads_the_body(
    integration_client,
    api_client,
    settings,
):
    """A garbage token with an oversized body is 401, never a buffered 400."""

    settings.MEDIA_MAX_UPLOAD_BYTES = 1024
    settings.DATA_UPLOAD_MAX_MEMORY_SIZE = 1024
    media = _create_media(integration_client, size_bytes=1024)

    response = api_client.put(
        f"{MEDIA_URL}upload/not-a-token/",
        data=b"x" * 4096,
        content_type="application/octet-stream",
    )

    assert response.status_code == 401
    assert response.json()["code"] == "AUTHENTICATION_REQUIRED"
    row = MediaFile.objects.get(pk=media["id"])
    assert get_storage_adapter().verify_object(row.storage_key) is None


@pytest.mark.django_db
def test_a_second_upload_contract_is_refused_once_the_object_exists(
    integration_client,
    api_client,
):
    media = _create_media(integration_client)
    contract = integration_client.get(f"{MEDIA_URL}{media['id']}/upload-url/").json()
    stored = api_client.put(
        contract["upload_url"],
        data=PNG_PAYLOAD,
        content_type="application/octet-stream",
    )
    assert stored.status_code == 204

    repeated = integration_client.get(f"{MEDIA_URL}{media['id']}/upload-url/")

    assert repeated.status_code == 409
    assert repeated.json()["code"] == "CONTENT_CONFLICT"
    row = MediaFile.objects.get(pk=media["id"])
    with get_storage_adapter().read_object(row.storage_key) as content:
        assert content.read() == PNG_PAYLOAD


@pytest.mark.django_db
def test_upload_contract_rejects_bytes_that_do_not_match_the_declared_size(
    integration_client,
    api_client,
):
    media = _create_media(integration_client, size_bytes=64)
    contract = integration_client.get(f"{MEDIA_URL}{media['id']}/upload-url/").json()

    response = api_client.put(
        contract["upload_url"],
        data=b"x" * 63,
        content_type="application/octet-stream",
    )

    assert response.status_code == 422
    assert response.json()["code"] == "MEDIA_INVALID"
    assert response.json()["fields"]["size_bytes"]


@pytest.mark.django_db
def test_capability_urls_are_rejected_once_expired(
    integration_client,
    api_client,
    settings,
):
    media = _create_media(integration_client)
    contract = integration_client.get(f"{MEDIA_URL}{media['id']}/upload-url/").json()
    uploaded = api_client.put(
        contract["upload_url"],
        data=PNG_PAYLOAD,
        content_type="application/octet-stream",
    )
    assert uploaded.status_code == 204
    signed = api_client.get(f"{MEDIA_URL}{media['id']}/access-url/").json()

    settings.MEDIA_UPLOAD_URL_TTL = -1
    settings.MEDIA_ACCESS_URL_TTL = -1

    expired_upload = api_client.put(
        contract["upload_url"],
        data=PNG_PAYLOAD,
        content_type="application/octet-stream",
    )
    expired_download = api_client.get(signed["access_url"])

    assert expired_upload.status_code == 401
    assert expired_upload.json()["code"] == "AUTHENTICATION_REQUIRED"
    assert expired_download.status_code == 401
    assert expired_download.json()["code"] == "AUTHENTICATION_REQUIRED"


# ---------------------------------------------------------------------------
# Metadata surface, strict payloads and the documented 404s.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_media_responses_never_expose_the_storage_key(integration_client, media_file):
    media = _create_media(integration_client)

    detail = integration_client.get(f"{MEDIA_URL}{media['id']}/")
    assert detail.status_code == 200

    for body in (media, detail.json()):
        assert "storage_key" not in body
        assert set(body) == {
            "id",
            "original_name",
            "mime_type",
            "size_bytes",
            "checksum",
            "visibility",
            "created_at",
            "updated_at",
        }

    row = MediaFile.objects.get(pk=media["id"])
    assert row.storage_key
    assert row.storage_key not in detail.content.decode()


@pytest.mark.django_db
def test_unknown_top_level_field_is_rejected(integration_client):
    response = integration_client.post(
        MEDIA_URL,
        {"mime_type": "image/png", "size_bytes": 16, "storage_key": "client/chosen"},
        format="json",
    )

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert "storage_key" in response.json()["fields"]
    assert not MediaFile.objects.exists()


@pytest.mark.django_db
def test_unsupported_mime_type_is_rejected_over_http(integration_client):
    response = integration_client.post(
        MEDIA_URL,
        {"mime_type": "text/html", "size_bytes": 16},
        format="json",
    )

    assert response.status_code == 422
    assert response.json()["code"] == "MEDIA_INVALID"
    assert response.json()["fields"]["mime_type"]
    assert not MediaFile.objects.exists()


@pytest.mark.django_db
def test_media_detail_and_repeated_delete_follow_the_404_convention(
    integration_client,
):
    media = _create_media(integration_client)

    assert integration_client.get(f"{MEDIA_URL}{media['id']}/").status_code == 200
    assert integration_client.delete(f"{MEDIA_URL}{media['id']}/").status_code == 204

    missing = integration_client.get(f"{MEDIA_URL}{media['id']}/")
    repeated = integration_client.delete(f"{MEDIA_URL}{media['id']}/")
    assert missing.status_code == 404
    assert missing.json()["code"] == "RESOURCE_NOT_FOUND"
    assert repeated.status_code == 404
    assert repeated.json()["code"] == "RESOURCE_NOT_FOUND"


@pytest.mark.django_db
def test_controlled_endpoints_are_404_on_a_backend_without_the_contract(
    integration_client,
    api_client,
    monkeypatch,
):
    media = _create_media(integration_client)
    contract = integration_client.get(f"{MEDIA_URL}{media['id']}/upload-url/").json()

    class _PresignOnlyAdapter:
        supports_controlled_upload = False

    monkeypatch.setattr(
        "apps.media.services.get_storage_adapter",
        _PresignOnlyAdapter,
    )

    response = api_client.put(
        contract["upload_url"],
        data=PNG_PAYLOAD,
        content_type="application/octet-stream",
    )

    assert response.status_code == 404
    assert response.json()["code"] == "RESOURCE_NOT_FOUND"


# ---------------------------------------------------------------------------
# Permissions of the authoring routes and the access-url scope.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_authoring_routes_require_the_integration_key_or_an_author(
    api_client,
    authenticate,
    editor,
    make_user,
):
    body = {"mime_type": "image/png", "size_bytes": 16}

    anonymous = api_client.post(MEDIA_URL, body, format="json")
    assert anonymous.status_code == 401
    assert anonymous.json()["code"] == "AUTHENTICATION_REQUIRED"

    authenticate(api_client, make_user(username="plain-user"))
    plain_user = api_client.post(MEDIA_URL, body, format="json")
    assert plain_user.status_code == 403
    assert plain_user.json()["code"] == "PERMISSION_DENIED"

    api_client.credentials()
    authenticate(api_client, editor)
    assert api_client.post(MEDIA_URL, body, format="json").status_code == 201


@pytest.mark.django_db
def test_a_wrong_integration_key_is_rejected_before_the_jwt_path(
    api_client,
    authenticate,
    editor,
):
    authenticate(api_client, editor)
    api_client.credentials(HTTP_X_MEDCORE_INTEGRATION_KEY="wrong-key")

    response = api_client.post(
        MEDIA_URL,
        {"mime_type": "image/png", "size_bytes": 16},
        format="json",
    )

    assert response.status_code == 401
    assert response.json()["code"] == "INTEGRATION_KEY_INVALID"


@pytest.mark.django_db
def test_access_url_rejects_the_integration_principal(integration_client, stored_media):
    media, _ = stored_media(visibility=PUBLIC)

    response = integration_client.get(f"{MEDIA_URL}{media.pk}/access-url/")

    assert response.status_code == 403
    assert response.json()["code"] == "INTEGRATION_SCOPE_FORBIDDEN"


# ---------------------------------------------------------------------------
# The access matrix of GET /api/v1/media/{id}/access-url/.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_public_media_is_signed_for_an_anonymous_actor(stored_media, api_client):
    media, _ = stored_media(visibility=PUBLIC)

    response = api_client.get(f"{MEDIA_URL}{media.pk}/access-url/")

    assert response.status_code == 200
    assert response.json()["access_url"].startswith(
        "http://testserver/api/v1/media/file/"
    )


@pytest.mark.django_db
def test_protected_media_without_a_readable_reference_requires_authentication(
    stored_media,
    api_client,
):
    media, _ = stored_media(visibility=PROTECTED)

    response = api_client.get(f"{MEDIA_URL}{media.pk}/access-url/")

    assert response.status_code == 401
    assert response.json()["code"] == "AUTHENTICATION_REQUIRED"


@pytest.mark.django_db
def test_protected_media_with_a_published_preview_reference_is_signed_anonymously(
    stored_media,
    media_reference,
    api_client,
):
    media, payload = stored_media(visibility=PROTECTED)
    media_reference(media, access_level="free", is_demo_preview=True)

    response = api_client.get(f"{MEDIA_URL}{media.pk}/access-url/")

    assert response.status_code == 200
    downloaded = api_client.get(response.json()["access_url"])
    assert downloaded.status_code == 200
    assert _bytes_of(downloaded) == payload


@pytest.mark.django_db
def test_protected_media_with_topic_access_is_signed_for_a_user(
    stored_media,
    media_reference,
    api_client,
    authenticate,
    make_user,
):
    media, _ = stored_media(visibility=PROTECTED)
    media_reference(media, access_level="free")
    authenticate(api_client, make_user(username="reader-with-access"))

    response = api_client.get(f"{MEDIA_URL}{media.pk}/access-url/")

    assert response.status_code == 200
    assert response.json()["method"] == "GET"


@pytest.mark.django_db
def test_protected_media_without_access_is_denied_for_a_user(
    stored_media,
    media_reference,
    api_client,
    authenticate,
    make_user,
):
    media, _ = stored_media(visibility=PROTECTED)
    media_reference(media, access_level="paid")
    authenticate(api_client, make_user(username="reader-without-access"))

    response = api_client.get(f"{MEDIA_URL}{media.pk}/access-url/")

    assert response.status_code == 403
    assert response.json()["code"] == "MEDIA_ACCESS_DENIED"


@pytest.mark.django_db
def test_access_url_is_422_when_the_object_is_missing(media_file, api_client):
    media = media_file(visibility=PUBLIC)

    response = api_client.get(f"{MEDIA_URL}{media.pk}/access-url/")

    assert response.status_code == 422
    assert response.json()["code"] == "MEDIA_INVALID"


@pytest.mark.django_db
def test_access_url_fails_closed_when_the_access_provider_is_unset(
    stored_media,
    api_client,
    settings,
):
    settings.MEDIA_ACCESS_POLICY_PROVIDER = ""
    media, _ = stored_media(visibility=PROTECTED)

    response = api_client.get(f"{MEDIA_URL}{media.pk}/access-url/")

    assert response.status_code == 403
    assert response.json()["code"] == "MEDIA_ACCESS_DENIED"


@pytest.mark.django_db
def test_delete_fails_closed_when_the_guard_provider_is_unset(
    integration_client,
    stored_media,
    settings,
):
    settings.MEDIA_DELETE_GUARD_PROVIDER = ""
    media, _ = stored_media()

    response = integration_client.delete(f"{MEDIA_URL}{media.pk}/")

    assert response.status_code == 409
    assert response.json()["code"] == "CONTENT_CONFLICT"
    assert MediaFile.objects.filter(pk=media.pk).exists()


@pytest.mark.django_db
def test_delete_refuses_a_published_reference_and_allows_the_detached_repair(
    integration_client,
    stored_media,
    media_reference,
):
    media, _ = stored_media(visibility=PROTECTED)
    block = media_reference(media)

    refused = integration_client.delete(f"{MEDIA_URL}{media.pk}/")
    assert refused.status_code == 409
    assert refused.json()["code"] == "CONTENT_CONFLICT"

    block.media = None
    block.save(update_fields=["media"])

    assert integration_client.delete(f"{MEDIA_URL}{media.pk}/").status_code == 204
    assert not MediaFile.objects.filter(pk=media.pk).exists()


# ---------------------------------------------------------------------------
# Throttling.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_media_upload_scope_is_throttled(integration_client):
    body = {"mime_type": "image/png", "size_bytes": 16}

    responses = [
        integration_client.post(MEDIA_URL, body, format="json") for _ in range(31)
    ]

    assert [response.status_code for response in responses[:30]] == [201] * 30
    assert responses[30].status_code == 429
    assert responses[30].json()["code"] == "THROTTLED"


# ---------------------------------------------------------------------------
# OpenAPI coverage of the seven documented media routes.
# ---------------------------------------------------------------------------

MEDIA_SCHEMA_PATHS = {
    "/api/v1/media/": {"post"},
    "/api/v1/media/{id}/": {"get", "delete"},
    "/api/v1/media/{id}/upload-url/": {"get"},
    "/api/v1/media/{id}/access-url/": {"get"},
    "/api/v1/media/upload/{token}/": {"put"},
    "/api/v1/media/file/{token}/": {"get"},
}


@pytest.mark.django_db
def test_openapi_contains_every_media_path_and_method(api_client):
    response = api_client.get("/api/v1/schema/", HTTP_ACCEPT="application/json")

    assert response.status_code == 200
    paths = json.loads(response.content)["paths"]

    for path, methods in MEDIA_SCHEMA_PATHS.items():
        assert path in paths, f"{path} is missing from the schema"
        assert methods <= set(paths[path]), f"{path} lacks {methods - set(paths[path])}"
