from __future__ import annotations

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.common.exceptions import APIError
from apps.content.access import resolve_topic_blocks
from apps.content.selectors import (
    get_published_topic,
    get_section,
    get_subject,
    list_published_topics,
    list_subjects,
    search_titles,
    topic_sources,
)
from apps.content.serializers import (
    SearchResultSerializer,
    SectionSerializer,
    SubjectSerializer,
    TopicContentSerializer,
    TopicSerializer,
)

ERROR_RESPONSES = {
    401: OpenApiResponse(description="Authentication required."),
    403: OpenApiResponse(description="Entitlement required."),
    404: OpenApiResponse(description="Resource not found."),
    422: OpenApiResponse(description="Invalid parent relation."),
    429: OpenApiResponse(description="Too many requests."),
}

SECTION_FILTER = OpenApiParameter(
    name="section_id",
    type=int,
    required=False,
    description="Restrict topics/search to one section.",
)
SUBJECT_FILTER = OpenApiParameter(
    name="subject_id",
    type=int,
    required=False,
    description="Restrict topics/search to one subject.",
)
QUERY_PARAM = OpenApiParameter(
    name="q",
    type=str,
    required=False,
    description="Case-insensitive title fragment.",
)


def _not_found() -> APIError:
    return APIError("Resource not found.", code="RESOURCE_NOT_FOUND", status_code=404)


def _parse_optional_int(request, name: str) -> int | None:
    raw = request.query_params.get(name)
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise APIError(
            f"Invalid {name}.",
            code="INVALID_RELATION",
            status_code=422,
        ) from exc


class SubjectListView(generics.GenericAPIView):
    permission_classes = (AllowAny,)
    throttle_scope = "catalog"
    serializer_class = SubjectSerializer

    @extend_schema(
        responses={200: SubjectSerializer(many=True), **ERROR_RESPONSES},
        description="Public paginated catalog of subjects ordered by position.",
    )
    def get(self, request):
        page = self.paginate_queryset(list_subjects())
        return self.get_paginated_response(self.get_serializer(page, many=True).data)


class SubjectDetailView(generics.GenericAPIView):
    permission_classes = (AllowAny,)
    throttle_scope = "catalog"
    serializer_class = SubjectSerializer

    @extend_schema(responses={200: SubjectSerializer, **ERROR_RESPONSES})
    def get(self, request, pk: int):
        subject = get_subject(pk)
        if subject is None:
            raise _not_found()
        return Response(self.get_serializer(subject).data)


class SectionDetailView(generics.GenericAPIView):
    permission_classes = (AllowAny,)
    throttle_scope = "catalog"
    serializer_class = SectionSerializer

    @extend_schema(responses={200: SectionSerializer, **ERROR_RESPONSES})
    def get(self, request, pk: int):
        section = get_section(pk)
        if section is None:
            raise _not_found()
        return Response(self.get_serializer(section).data)


class TopicListView(generics.GenericAPIView):
    permission_classes = (AllowAny,)
    throttle_scope = "catalog"
    serializer_class = TopicSerializer

    @extend_schema(
        parameters=[SECTION_FILTER, SUBJECT_FILTER],
        responses={200: TopicSerializer(many=True), **ERROR_RESPONSES},
        description="Public paginated list of published topics.",
    )
    def get(self, request):
        section_id = _parse_optional_int(request, "section_id")
        subject_id = _parse_optional_int(request, "subject_id")
        if section_id is not None and get_section(section_id) is None:
            raise APIError(
                "Unknown section_id.",
                code="INVALID_RELATION",
                status_code=422,
            )
        if subject_id is not None and get_subject(subject_id) is None:
            raise APIError(
                "Unknown subject_id.",
                code="INVALID_RELATION",
                status_code=422,
            )
        queryset = list_published_topics(
            section_id=section_id,
            subject_id=subject_id,
        )
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)


class TopicDetailView(generics.GenericAPIView):
    permission_classes = (AllowAny,)
    throttle_scope = "catalog"
    serializer_class = TopicSerializer

    @extend_schema(responses={200: TopicSerializer, **ERROR_RESPONSES})
    def get(self, request, pk: int):
        topic = get_published_topic(pk)
        if topic is None:
            raise _not_found()
        return Response(self.get_serializer(topic).data)


class TopicContentView(generics.GenericAPIView):
    permission_classes = (AllowAny,)
    throttle_scope = "content_read"
    serializer_class = TopicContentSerializer

    @extend_schema(
        responses={200: TopicContentSerializer, **ERROR_RESPONSES},
        description=(
            "Ordered published theory for a Topic, filtered by the Topic access "
            "policy. Anonymous reads receive the demo-preview subset only."
        ),
    )
    def get(self, request, pk: int):
        topic = get_published_topic(pk)
        if topic is None:
            raise _not_found()
        decision, blocks = resolve_topic_blocks(topic, request.user)
        payload = {
            "topic": topic,
            "access": {
                "level": decision.level,
                "full_access": decision.full_access,
                "is_demo_preview": decision.is_demo_preview,
            },
            "sources": topic_sources(topic),
            "blocks": blocks,
        }
        return Response(self.get_serializer(payload).data)


class SearchView(generics.GenericAPIView):
    permission_classes = (AllowAny,)
    throttle_scope = "search"
    serializer_class = SearchResultSerializer

    @extend_schema(
        parameters=[QUERY_PARAM, SUBJECT_FILTER, SECTION_FILTER],
        responses={200: SearchResultSerializer(many=True), **ERROR_RESPONSES},
        description="Case-insensitive title search over subjects, sections and topics.",
    )
    def get(self, request):
        query = (request.query_params.get("q") or "").strip()
        results = search_titles(
            query=query,
            subject_id=_parse_optional_int(request, "subject_id"),
            section_id=_parse_optional_int(request, "section_id"),
        )
        page = self.paginate_queryset(results)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)
