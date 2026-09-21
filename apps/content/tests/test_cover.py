from __future__ import annotations

import pytest

from apps.content.models import Topic
from apps.media.models import MediaFile


def _media() -> MediaFile:
    return MediaFile.objects.create(
        storage_key=f"covers/{MediaFile.objects.count() + 1}.png",
        original_name="cover.png",
        mime_type="image/png",
        size_bytes=12,
        visibility=MediaFile.Visibility.PUBLIC,
    )


@pytest.mark.django_db
def test_catalog_subject_and_topic_cover_is_null_by_default(api_client, catalog):
    topic = catalog["add_topic"](title="Demo", slug="demo", position=1)

    subject = api_client.get(f"/api/v1/subjects/{catalog['subject'].pk}/")
    listed = api_client.get("/api/v1/topics/")

    assert subject.status_code == 200
    assert subject.json()["cover"] is None
    assert listed.status_code == 200
    row = next(item for item in listed.json()["results"] if item["id"] == topic.pk)
    assert row["cover"] is None


@pytest.mark.django_db
def test_catalog_returns_cover_media_reference(api_client, catalog):
    media = _media()
    catalog["subject"].cover = media
    catalog["subject"].save(update_fields=["cover"])
    topic = catalog["add_topic"](title="Covered", slug="covered", position=1)
    topic.cover = media
    topic.save(update_fields=["cover"])

    subject = api_client.get(f"/api/v1/subjects/{catalog['subject'].pk}/").json()
    listed = api_client.get("/api/v1/topics/").json()["results"]
    row = next(item for item in listed if item["id"] == topic.pk)

    expected = {
        "id": media.pk,
        "mime_type": "image/png",
        "original_name": "cover.png",
        "visibility": "public",
    }
    assert subject["cover"] == expected
    assert row["cover"] == expected


@pytest.mark.django_db
def test_authoring_can_set_and_clear_cover(integration_client, catalog):
    media = _media()

    created = integration_client.post(
        "/api/v1/content/topics/",
        {
            "section": catalog["section"].pk,
            "title": "With cover",
            "status": Topic.Status.PUBLISHED,
            "access_level": Topic.AccessLevel.DEMO,
            "cover": media.pk,
        },
        format="json",
    )
    assert created.status_code == 201
    assert created.json()["cover"]["id"] == media.pk

    cleared = integration_client.patch(
        f"/api/v1/content/topics/{created.json()['id']}/",
        {"cover": None},
        format="json",
    )
    assert cleared.status_code == 200
    assert cleared.json()["cover"] is None
