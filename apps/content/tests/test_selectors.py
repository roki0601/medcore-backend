from __future__ import annotations

import pytest

from apps.common.exceptions import APIError
from apps.content import selectors
from apps.content.models import ContentBlock, Topic


@pytest.mark.django_db
def test_published_catalog_excludes_drafts_and_annotates_demo_preview(catalog):
    demo = catalog["add_topic"](title="Demo", slug="demo", position=1)
    free = catalog["add_topic"](
        title="Free",
        slug="free",
        position=2,
        access_level=Topic.AccessLevel.FREE,
    )
    catalog["add_topic"](
        title="Hidden",
        slug="hidden",
        position=3,
        status=Topic.Status.DRAFT,
    )
    catalog["add_block"](demo, block_type="markdown", position=1, body="# Demo")
    catalog["add_block"](
        free,
        block_type="markdown",
        position=1,
        body="# Free",
        demo=True,
    )

    topics = {topic.slug: topic for topic in selectors.list_published_topics()}

    assert set(topics) == {"demo", "free"}
    assert topics["demo"].has_demo_preview is False
    assert topics["free"].has_demo_preview is True


@pytest.mark.django_db
def test_topic_content_blocks_are_ordered_and_preview_filtered(catalog):
    topic = catalog["add_topic"](title="Free", slug="free", position=1)
    catalog["add_block"](
        topic,
        block_type="markdown",
        position=2,
        body="# Second",
    )
    catalog["add_block"](
        topic,
        block_type="callout",
        position=1,
        body="Preview",
        demo=True,
    )
    catalog["add_block"](
        topic,
        block_type="markdown",
        position=3,
        body="# Draft",
        status=ContentBlock.Status.DRAFT,
    )

    full = selectors.topic_content_blocks(topic, preview_only=False)
    preview = selectors.topic_content_blocks(topic, preview_only=True)

    assert [block.position for block in full] == [1, 2]
    assert [block.position for block in preview] == [1]
    assert preview[0].markdown_body == "Preview"


@pytest.mark.django_db
def test_search_returns_grouped_title_matches_and_published_topics_only(catalog):
    catalog["add_topic"](title="Beta-lactams", slug="beta", position=1)
    catalog["add_topic"](
        title="Hidden beta",
        slug="hidden-beta",
        position=2,
        status=Topic.Status.DRAFT,
    )

    results = selectors.search_titles(query="beta")

    assert [item["type"] for item in results] == ["topic"]
    assert results[0]["title"] == "Beta-lactams"
    assert results[0]["subject_id"] == catalog["subject"].pk
    assert results[0]["section_id"] == catalog["section"].pk


@pytest.mark.django_db
def test_search_filters_by_subject_and_section(catalog):
    catalog["add_topic"](title="Macrolides", slug="macrolides", position=1)

    assert selectors.search_titles(query="pharm")
    assert selectors.search_titles(query="mac", subject_id=catalog["subject"].pk)
    assert selectors.search_titles(query="mac", section_id=catalog["section"].pk)


@pytest.mark.django_db
def test_search_rejects_unknown_filters_and_empty_query(catalog):
    assert selectors.search_titles(query="") == []
    with pytest.raises(APIError) as exc:
        selectors.search_titles(query="x", subject_id=999999)
    assert exc.value.default_code == "INVALID_RELATION"
    assert exc.value.status_code == 422
