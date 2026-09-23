import pytest

from apps.content import services
from apps.content.models import Topic


@pytest.mark.django_db
def test_cyrillic_title_gets_a_latin_slug_that_stays_stable():
    subject = services.save_subject(title="Микробиология")
    renamed = services.save_subject(title="Микробиология общая", instance=subject)

    assert subject.slug == "mikrobiologiya"
    assert renamed.slug == "mikrobiologiya"
    assert renamed.title == "Микробиология общая"


@pytest.mark.django_db
def test_reserved_subject_slug_is_suffixed():
    subject = services.save_subject(title="Catalog")

    assert subject.slug == "catalog-2"


@pytest.mark.django_db
def test_subject_and_topic_lookup_by_slug(api_client, catalog):
    published = catalog["add_topic"](
        title="Beta-lactams",
        slug="beta-lactams",
        position=1,
    )
    catalog["add_topic"](
        title="Hidden",
        slug="hidden",
        position=2,
        status=Topic.Status.DRAFT,
    )

    subject = api_client.get("/api/v1/subjects/by-slug/pharmacology/")
    topic = api_client.get("/api/v1/topics/by-slug/pharmacology/beta-lactams/")
    missing_subject = api_client.get("/api/v1/subjects/by-slug/missing/")
    missing_topic = api_client.get("/api/v1/topics/by-slug/pharmacology/missing/")
    draft = api_client.get("/api/v1/topics/by-slug/pharmacology/hidden/")

    assert subject.status_code == 200
    body = subject.json()
    assert body["subject"]["slug"] == "pharmacology"
    assert body["sections"][0]["slug"] == "antibiotics"
    assert [item["slug"] for item in body["sections"][0]["topics"]] == ["beta-lactams"]
    assert topic.status_code == 200
    assert topic.json()["topic"]["id"] == published.pk
    assert topic.json()["subject"]["slug"] == "pharmacology"
    assert topic.json()["previous"] is None
    assert topic.json()["next"] is None
    assert missing_subject.status_code == 404
    assert missing_topic.status_code == 404
    assert draft.status_code == 404
    numeric = api_client.get(f"/api/v1/subjects/{catalog['subject'].pk}/")
    assert numeric.status_code == 200


@pytest.mark.django_db
def test_topic_neighbors_follow_published_order(api_client, catalog):
    catalog["add_topic"](title="First", slug="first", position=1)
    catalog["add_topic"](title="Second", slug="second", position=2)
    catalog["add_topic"](
        title="Draft",
        slug="draft",
        position=3,
        status=Topic.Status.DRAFT,
    )
    catalog["add_topic"](title="Third", slug="third", position=4)

    middle = api_client.get("/api/v1/topics/by-slug/pharmacology/second/")

    assert middle.status_code == 200
    assert middle.json()["previous"]["slug"] == "first"
    assert middle.json()["next"]["slug"] == "third"


@pytest.mark.django_db
def test_sitemap_lists_published_slugs_only(api_client, catalog):
    catalog["add_topic"](title="Visible", slug="visible", position=1)
    catalog["add_topic"](
        title="Hidden",
        slug="hidden",
        position=2,
        status=Topic.Status.DRAFT,
    )

    response = api_client.get("/api/v1/catalog/sitemap/")

    assert response.status_code == 200
    body = response.json()
    assert [item["slug"] for item in body["subjects"]] == ["pharmacology"]
    assert body["subjects"][0]["updated_at"]
    assert [item["slug"] for item in body["topics"]] == ["visible"]
    assert body["topics"][0]["subject_slug"] == "pharmacology"
    assert body["topics"][0]["updated_at"]
    assert "hidden" not in response.content.decode()
