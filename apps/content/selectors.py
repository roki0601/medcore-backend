from __future__ import annotations

from django.db.models import Exists, OuterRef, QuerySet

from apps.common.exceptions import APIError
from apps.content.models import ContentBlock, Section, Source, Subject, Topic


def list_subjects() -> QuerySet[Subject]:
    return Subject.objects.select_related("cover")


def get_subject(subject_id: int) -> Subject | None:
    return Subject.objects.select_related("cover").filter(pk=subject_id).first()


def get_section(section_id: int) -> Section | None:
    return Section.objects.select_related("subject").filter(pk=section_id).first()


def _published_demo_preview_exists():
    return ContentBlock.objects.filter(
        topic=OuterRef("pk"),
        status=ContentBlock.Status.PUBLISHED,
        is_demo_preview=True,
    )


def published_topics() -> QuerySet[Topic]:
    return (
        Topic.objects.filter(status=Topic.Status.PUBLISHED)
        .select_related("section", "section__subject", "cover")
        .annotate(has_demo_preview=Exists(_published_demo_preview_exists()))
    )


def list_published_topics(
    *,
    section_id: int | None = None,
    subject_id: int | None = None,
) -> QuerySet[Topic]:
    queryset = published_topics()
    if section_id is not None:
        queryset = queryset.filter(section_id=section_id)
    if subject_id is not None:
        queryset = queryset.filter(section__subject_id=subject_id)
    return queryset


def get_published_topic(topic_id: int) -> Topic | None:
    return published_topics().filter(pk=topic_id).first()


def topic_content_blocks(
    topic: Topic,
    *,
    preview_only: bool,
) -> list[ContentBlock]:
    queryset = (
        ContentBlock.objects.filter(
            topic=topic,
            status=ContentBlock.Status.PUBLISHED,
        )
        .select_related("block_type", "media")
        .prefetch_related("sources")
        .order_by("position", "id")
    )
    if preview_only:
        queryset = queryset.filter(is_demo_preview=True)
    return list(queryset)


def topic_sources(topic: Topic) -> list[Source]:
    return list(topic.sources.all().order_by("id"))


def _require_relation(model, value: int, field: str):
    instance = model.objects.filter(pk=value).first()
    if instance is None:
        raise APIError(
            f"Unknown {field}.",
            code="INVALID_RELATION",
            status_code=422,
        )
    return instance


def search_titles(
    *,
    query: str,
    subject_id: int | None = None,
    section_id: int | None = None,
) -> list[dict]:
    """Return grouped title matches for subjects, sections and topics."""

    subject = None
    section = None
    if subject_id is not None:
        subject = _require_relation(Subject, subject_id, "subject_id")
    if section_id is not None:
        section = _require_relation(Section, section_id, "section_id")

    if not query:
        return []

    subjects = Subject.objects.filter(title__icontains=query)
    sections = Section.objects.select_related("subject").filter(title__icontains=query)
    topics = published_topics().filter(title__icontains=query)

    if subject is not None:
        subjects = subjects.filter(pk=subject.pk)
        sections = sections.filter(subject=subject)
        topics = topics.filter(section__subject=subject)
    if section is not None:
        subjects = subjects.filter(pk=section.subject_id)
        sections = sections.filter(pk=section.pk)
        topics = topics.filter(section=section)

    results: list[dict] = []
    for item in subjects.order_by("position", "id"):
        results.append(
            {
                "type": "subject",
                "id": item.pk,
                "title": item.title,
                "subject_id": item.pk,
                "section_id": None,
                "access_level": None,
                "has_demo_preview": None,
            }
        )
    for item in sections.order_by("position", "id"):
        results.append(
            {
                "type": "section",
                "id": item.pk,
                "title": item.title,
                "subject_id": item.subject_id,
                "section_id": item.pk,
                "access_level": None,
                "has_demo_preview": None,
            }
        )
    for item in topics.order_by("position", "id"):
        results.append(
            {
                "type": "topic",
                "id": item.pk,
                "title": item.title,
                "subject_id": item.section.subject_id,
                "section_id": item.section_id,
                "access_level": item.access_level,
                "has_demo_preview": item.has_demo_preview,
            }
        )
    return results
