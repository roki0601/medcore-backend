from __future__ import annotations

import pytest
from drf_spectacular.generators import SchemaGenerator
from rest_framework.throttling import ScopedRateThrottle

from apps.content import access, services
from apps.content.admin import ContentBlockAdminForm
from apps.content.models import ContentBlock, ContentBlockType, Source, Topic
from apps.media.models import MediaFile


def _content_url(topic) -> str:
    return f"/api/v1/topics/{topic.pk}/content/"


@pytest.mark.django_db
def test_catalog_is_public_paginated_and_hides_drafts(api_client, catalog):
    catalog["add_topic"](title="Demo", slug="demo", position=1)
    catalog["add_topic"](
        title="Hidden",
        slug="hidden",
        position=2,
        status=Topic.Status.DRAFT,
    )

    subjects = api_client.get("/api/v1/subjects/")
    topics = api_client.get("/api/v1/topics/")

    assert subjects.status_code == 200
    assert subjects.json()["count"] == 1
    assert subjects.json()["results"][0]["slug"] == "pharmacology"
    assert topics.status_code == 200
    assert [item["slug"] for item in topics.json()["results"]] == ["demo"]
    assert topics.json()["results"][0]["has_demo_preview"] is False


@pytest.mark.django_db
def test_catalog_detail_and_missing_resource_envelope(api_client, catalog):
    subject_url = f"/api/v1/subjects/{catalog['subject'].pk}/"
    section_url = f"/api/v1/sections/{catalog['section'].pk}/"
    assert api_client.get(subject_url).status_code == 200
    assert api_client.get(section_url).status_code == 200
    missing = api_client.get("/api/v1/subjects/999999/")
    assert missing.status_code == 404
    assert missing.json()["code"] == "RESOURCE_NOT_FOUND"


@pytest.mark.django_db
def test_topic_list_rejects_invalid_and_unknown_filters(api_client, catalog):
    malformed = api_client.get("/api/v1/topics/?section_id=abc")
    assert malformed.status_code == 422
    assert malformed.json()["code"] == "INVALID_RELATION"

    unknown = api_client.get("/api/v1/topics/?section_id=999999")
    assert unknown.status_code == 422
    assert unknown.json()["code"] == "INVALID_RELATION"


@pytest.mark.django_db
def test_draft_topic_is_hidden_from_detail_and_content(api_client, catalog):
    topic = catalog["add_topic"](
        title="Hidden",
        slug="hidden",
        position=1,
        status=Topic.Status.DRAFT,
    )
    catalog["add_block"](topic, block_type="markdown", position=1, body="# Secret")

    assert api_client.get(f"/api/v1/topics/{topic.pk}/").status_code == 404
    content = api_client.get(_content_url(topic))
    assert content.status_code == 404
    assert content.json()["code"] == "RESOURCE_NOT_FOUND"


@pytest.mark.django_db
def test_demo_topic_returns_all_published_blocks_to_anonymous(api_client, catalog):
    topic = catalog["add_topic"](title="Demo", slug="demo", position=1)
    catalog["add_block"](topic, block_type="markdown", position=1, body="# One")
    catalog["add_block"](
        topic,
        block_type="callout",
        position=2,
        body="Two",
        status=ContentBlock.Status.REVIEWED,
    )
    catalog["add_block"](
        topic,
        block_type="markdown",
        position=3,
        body="# Three",
        status=ContentBlock.Status.GENERATED,
    )

    response = api_client.get(_content_url(topic))

    assert response.status_code == 200
    body = response.json()
    assert body["access"] == {
        "level": "demo",
        "full_access": True,
        "is_demo_preview": False,
    }
    assert [block["position"] for block in body["blocks"]] == [1]
    assert body["blocks"][0]["markdown_body"] == "# One"


@pytest.mark.django_db
def test_published_topic_without_blocks_returns_empty_list(api_client, catalog):
    topic = catalog["add_topic"](title="Empty", slug="empty", position=1)

    response = api_client.get(_content_url(topic))

    assert response.status_code == 200
    assert response.json()["blocks"] == []


@pytest.mark.django_db
def test_topic_content_includes_attached_sources(api_client, catalog):
    topic = catalog["add_topic"](title="Demo", slug="demo", position=1)
    block = catalog["add_block"](
        topic,
        block_type="markdown",
        position=1,
        body="# One",
    )
    topic_source = services.save_source(
        title="Textbook",
        source_type=Source.SourceType.TEXTBOOK,
        author="Author",
        year=2024,
    )
    block_source = services.save_source(
        title="Article",
        source_type=Source.SourceType.ARTICLE,
        url="https://example.org/a",
    )
    services.attach_source(topic_source, topic=topic)
    services.attach_source(block_source, block=block)

    response = api_client.get(_content_url(topic))

    assert response.status_code == 200
    body = response.json()
    assert [item["title"] for item in body["sources"]] == ["Textbook"]
    assert [item["title"] for item in body["blocks"][0]["sources"]] == ["Article"]


@pytest.mark.django_db
def test_anonymous_free_topic_gets_only_published_preview_blocks(api_client, catalog):
    topic = catalog["add_topic"](
        title="Free",
        slug="free",
        position=1,
        access_level=Topic.AccessLevel.FREE,
    )
    catalog["add_block"](topic, block_type="markdown", position=1, body="# Full")
    catalog["add_block"](
        topic,
        block_type="callout",
        position=2,
        body="Preview",
        demo=True,
    )

    response = api_client.get(_content_url(topic))

    assert response.status_code == 200
    body = response.json()
    assert body["access"]["is_demo_preview"] is True
    assert body["access"]["full_access"] is False
    assert [block["position"] for block in body["blocks"]] == [2]
    assert "# Full" not in response.content.decode()


@pytest.mark.django_db
def test_anonymous_free_topic_without_preview_requires_authentication(
    api_client, catalog
):
    topic = catalog["add_topic"](
        title="Free",
        slug="free",
        position=1,
        access_level=Topic.AccessLevel.FREE,
    )
    catalog["add_block"](topic, block_type="markdown", position=1, body="# Full")

    response = api_client.get(_content_url(topic))

    assert response.status_code == 401
    assert response.json()["code"] == "AUTHENTICATION_REQUIRED"


@pytest.mark.django_db
def test_free_topic_returns_full_body_to_authenticated_user(
    api_client,
    catalog,
    make_user,
    authenticate,
):
    user = make_user(username="reader")
    authenticate(api_client, user)
    topic = catalog["add_topic"](
        title="Free",
        slug="free",
        position=1,
        access_level=Topic.AccessLevel.FREE,
    )
    catalog["add_block"](topic, block_type="markdown", position=1, body="# Full")

    response = api_client.get(_content_url(topic))

    assert response.status_code == 200
    assert response.json()["access"]["full_access"] is True
    assert [block["position"] for block in response.json()["blocks"]] == [1]


@pytest.mark.django_db
def test_paid_topic_requires_entitlement_and_allow_path_uses_policy_seam(
    api_client,
    catalog,
    make_user,
    authenticate,
    monkeypatch,
):
    user = make_user(username="reader")
    authenticate(api_client, user)
    topic = catalog["add_topic"](
        title="Paid",
        slug="paid",
        position=1,
        access_level=Topic.AccessLevel.PAID,
    )
    catalog["add_block"](topic, block_type="markdown", position=1, body="# Paid")

    denied = api_client.get(_content_url(topic))
    assert denied.status_code == 403
    assert denied.json()["code"] == "TOPIC_ENTITLEMENT_REQUIRED"

    monkeypatch.setattr(access, "has_paid_content_entitlement", lambda actor: True)
    allowed = api_client.get(_content_url(topic))
    assert allowed.status_code == 200
    assert allowed.json()["access"]["full_access"] is True


@pytest.mark.django_db
def test_paid_topic_allowed_with_real_subscription(
    api_client,
    catalog,
    make_user,
    authenticate,
):
    from datetime import timedelta
    from decimal import Decimal

    from django.utils import timezone

    from apps.subscriptions.models import Plan, Subscription

    user = make_user(username="paid_member")
    authenticate(api_client, user)
    plan = Plan.objects.create(
        code="vip-month",
        title="VIP Month",
        price_rub=Decimal("990.00"),
        duration_days=30,
        is_active=True,
    )
    now = timezone.now()
    Subscription.objects.create(
        user=user,
        plan=plan,
        status=Subscription.Status.ACTIVE,
        starts_at=now - timedelta(days=1),
        expires_at=now + timedelta(days=29),
    )

    topic = catalog["add_topic"](
        title="Paid Topic Real API",
        slug="paid-api",
        position=1,
        access_level=Topic.AccessLevel.PAID,
    )
    catalog["add_block"](topic, block_type="markdown", position=1, body="# Paid API")

    response = api_client.get(_content_url(topic))
    assert response.status_code == 200
    assert response.json()["access"]["full_access"] is True
    assert len(response.json()["blocks"]) == 1


@pytest.mark.django_db
def test_image_block_exposes_reference_without_storage_key(api_client, catalog):
    topic = catalog["add_topic"](title="Demo", slug="demo", position=1)
    media = MediaFile.objects.create(
        storage_key="k/secret.png",
        original_name="secret.png",
        mime_type="image/png",
        size_bytes=12,
    )
    catalog["add_block"](
        topic,
        block_type="image",
        position=1,
        body="",
        media=media,
    )

    response = api_client.get(_content_url(topic))

    assert response.status_code == 200
    block = response.json()["blocks"][0]
    assert block["markdown_body"] is None
    assert block["media"] == {
        "id": media.pk,
        "mime_type": "image/png",
        "original_name": "secret.png",
        "visibility": MediaFile.Visibility.PROTECTED,
    }
    assert "storage_key" not in response.content.decode()
    assert "k/secret.png" not in response.content.decode()


@pytest.mark.django_db
def test_search_endpoint_filters_and_paginates(api_client, catalog):
    for index in range(3):
        catalog["add_topic"](
            title=f"Macrolide {index}",
            slug=f"macrolide-{index}",
            position=index + 1,
        )

    response = api_client.get("/api/v1/search/?q=macrol&page_size=2")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 3
    assert len(body["results"]) == 2
    assert {item["type"] for item in body["results"]} == {"topic"}

    invalid = api_client.get("/api/v1/search/?subject_id=999999")
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "INVALID_RELATION"


@pytest.mark.django_db
def test_catalog_requests_are_throttled(api_client, catalog, monkeypatch):
    monkeypatch.setattr(
        ScopedRateThrottle,
        "THROTTLE_RATES",
        {"catalog": "2/min"},
    )

    assert api_client.get("/api/v1/subjects/").status_code == 200
    assert api_client.get("/api/v1/subjects/").status_code == 200
    throttled = api_client.get("/api/v1/subjects/")

    assert throttled.status_code == 429
    assert throttled.json()["code"] == "THROTTLED"


@pytest.mark.django_db
def test_openapi_contains_content_paths():
    schema = SchemaGenerator().get_schema(request=None, public=True)
    paths = schema["paths"]

    assert "/api/v1/subjects/" in paths
    assert "/api/v1/subjects/{id}/" in paths
    assert "/api/v1/sections/{id}/" in paths
    assert "/api/v1/topics/" in paths
    assert "/api/v1/topics/{id}/" in paths
    assert "/api/v1/topics/{id}/content/" in paths
    assert "/api/v1/search/" in paths


@pytest.mark.django_db
def test_content_admin_requires_staff_and_editor_role(make_user):
    from django.test import Client

    editor = make_user(username="editor", role="editor", is_staff=True)
    staff_reader = make_user(username="staffreader", role="user", is_staff=True)
    non_staff_editor = make_user(username="plaineditor", role="editor")

    for user, expected in (
        (editor, 200),
        (staff_reader, 403),
        (non_staff_editor, 302),
    ):
        client = Client()
        client.force_login(user)
        response = client.get("/admin/content/subject/")
        assert response.status_code == expected


@pytest.mark.django_db
def test_content_admin_form_rejects_raw_html_and_unpublishable_blocks(catalog):
    topic = catalog["add_topic"](title="Demo", slug="demo", position=1)
    markdown_type = ContentBlockType.objects.get(key="markdown")
    image_type = ContentBlockType.objects.get(key="image")

    raw_html = ContentBlockAdminForm(
        data={
            "topic": topic.pk,
            "block_type": markdown_type.pk,
            "status": ContentBlock.Status.DRAFT,
            "markdown_body": "<script>alert(1)</script>",
            "caption": "",
        }
    )
    assert not raw_html.is_valid()
    assert "markdown_body" in raw_html.errors

    empty_publish = ContentBlockAdminForm(
        data={
            "topic": topic.pk,
            "block_type": markdown_type.pk,
            "status": ContentBlock.Status.PUBLISHED,
            "markdown_body": "   ",
            "caption": "",
        }
    )
    assert not empty_publish.is_valid()
    assert "markdown_body" in empty_publish.errors

    image_publish = ContentBlockAdminForm(
        data={
            "topic": topic.pk,
            "block_type": image_type.pk,
            "status": ContentBlock.Status.PUBLISHED,
            "markdown_body": "",
            "caption": "",
        }
    )
    assert not image_publish.is_valid()
    assert "media" in image_publish.errors
