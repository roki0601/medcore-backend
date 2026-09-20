from __future__ import annotations

from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.common.exceptions import APIError
from apps.common.integration import HasIntegrationKey, IntegrationKeyAuthentication
from apps.common.permissions import IsContentAuthor
from apps.common.serializers import APIErrorResponseSerializer
from apps.content.access import resolve_topic_blocks
from apps.content.models import (
    ContentBlock,
    Flashcard,
    Quiz,
    Section,
    Source,
    Subject,
    Topic,
)
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
    ContentBlockAuthoringSerializer,
    ContentBlockWriteSerializer,
    FlashcardSerializer,
    FlashcardWriteSerializer,
    QuizDetailSerializer,
    QuizSerializer,
    QuizWriteSerializer,
    SearchResultSerializer,
    SectionSerializer,
    SectionWriteSerializer,
    SourceAuthoringSerializer,
    SourceWriteSerializer,
    SubjectSerializer,
    SubjectWriteSerializer,
    TopicContentSerializer,
    TopicSerializer,
    TopicWriteSerializer,
)
from apps.content.services import (
    delete_content_block,
    delete_flashcard,
    delete_quiz,
    delete_section,
    delete_source,
    delete_subject,
    delete_topic,
    upsert_content_block,
    upsert_flashcard,
    upsert_quiz,
    upsert_section,
    upsert_source,
    upsert_subject,
    upsert_topic,
)
from apps.users.authentication import VersionedJWTAuthentication

ERROR_RESPONSES = {
    400: OpenApiResponse(
        response=APIErrorResponseSerializer, description="Invalid request."
    ),
    401: OpenApiResponse(
        response=APIErrorResponseSerializer, description="Authentication required."
    ),
    403: OpenApiResponse(
        response=APIErrorResponseSerializer, description="Entitlement required."
    ),
    404: OpenApiResponse(
        response=APIErrorResponseSerializer, description="Resource not found."
    ),
    422: OpenApiResponse(
        response=APIErrorResponseSerializer, description="Invalid parent relation."
    ),
    429: OpenApiResponse(
        response=APIErrorResponseSerializer, description="Too many requests."
    ),
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


# ---------------------------------------------------------------------------
# 004 authoring surface: the seven /api/v1/content/ collection and detail routes.
# ---------------------------------------------------------------------------

CONTENT_AUTHORING_AUTHENTICATION = (
    IntegrationKeyAuthentication,
    VersionedJWTAuthentication,
)
CONTENT_AUTHORING_PERMISSIONS = (HasIntegrationKey | IsContentAuthor,)

#: Named in every operation description of the authoring surface.
AUTHORING_PERMISSION = "Permission: integration key or editor/admin JWT."

#: The documented failures of the authoring surface. The 002 read surface has
#: its own mapping: a 403 here is a role failure, not an entitlement failure,
#: and a 409 is only reachable on a write.
AUTHORING_ERROR_RESPONSES = {
    400: OpenApiResponse(
        response=APIErrorResponseSerializer, description="Invalid request."
    ),
    401: OpenApiResponse(
        response=APIErrorResponseSerializer,
        description="Integration key invalid, or authentication missing.",
    ),
    403: OpenApiResponse(
        response=APIErrorResponseSerializer,
        description="The authenticated user is not an editor or an admin.",
    ),
    404: OpenApiResponse(
        response=APIErrorResponseSerializer, description="Resource not found."
    ),
    409: OpenApiResponse(
        response=APIErrorResponseSerializer,
        description="Content, external_id or publish-state conflict.",
    ),
    422: OpenApiResponse(
        response=APIErrorResponseSerializer, description="Invalid payload or relation."
    ),
    429: OpenApiResponse(
        response=APIErrorResponseSerializer, description="Too many requests."
    ),
}

CONTENT_PK_PARAMETER = OpenApiParameter(
    name="id",
    type=int,
    location=OpenApiParameter.PATH,
    description="Numeric identifier of the addressed row.",
)


def _pop_relation(data, field):
    """Split a resolved parent relation out of a validated payload."""

    payload = dict(data)
    return payload.pop(field), payload


class ContentListCreateView(generics.GenericAPIView):
    """Base of the seven authoring collections: paginated list and upserting create.

    A ``POST`` carrying an ``external_id`` that already exists updates that row
    and answers 200 instead of creating a duplicate.
    """

    authentication_classes = CONTENT_AUTHORING_AUTHENTICATION
    permission_classes = CONTENT_AUTHORING_PERMISSIONS
    throttle_scope = "integration_write"

    model = None
    write_serializer_class = None
    read_serializer_class = None

    def get_queryset(self):
        """Every row including drafts, in the model's ``Meta.ordering``."""

        return self.model.objects.all()

    def get(self, request):
        page = self.paginate_queryset(self.get_queryset())
        return self.get_paginated_response(
            self.read_serializer_class(page, many=True).data
        )

    def post(self, request):
        serializer = self.write_serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance, created = self.save_new(serializer.validated_data, request)
        return Response(
            self.read_serializer_class(instance).data,
            status=201 if created else 200,
        )

    def save_new(self, data, request):
        """Write a validated create payload and return ``(instance, created)``."""

        raise NotImplementedError


class ContentDetailView(generics.GenericAPIView):
    """Base of the seven authoring details: read, partial write and delete."""

    authentication_classes = CONTENT_AUTHORING_AUTHENTICATION
    permission_classes = CONTENT_AUTHORING_PERMISSIONS
    throttle_scope = "integration_write"

    model = None
    write_serializer_class = None
    read_serializer_class = None
    detail_serializer_class = None

    @property
    def detail_serializer(self):
        """The detail representation; quizzes use a richer one than the list."""

        return self.detail_serializer_class or self.read_serializer_class

    def get_object(self, pk: int):
        instance = self.model.objects.filter(pk=pk).first()
        if instance is None:
            raise _not_found()
        return instance

    def get(self, request, pk: int):
        return Response(self.detail_serializer(self.get_object(pk)).data)

    def patch(self, request, pk: int):
        instance = self.get_object(pk)
        serializer = self.write_serializer_class(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        instance = self.update_existing(instance, serializer.validated_data, request)
        return Response(self.detail_serializer(instance).data)

    def delete(self, request, pk: int):
        self.delete_existing(self.get_object(pk), request)
        return Response(status=204)

    def update_existing(self, instance, data, request):
        """Merge a validated partial payload with the stored row and write it."""

        raise NotImplementedError

    def delete_existing(self, instance, request):
        """Delete the addressed row through its service."""

        raise NotImplementedError


# --- subjects ---------------------------------------------------------------


@extend_schema_view(
    get=extend_schema(
        request=None,
        responses={200: SubjectSerializer(many=True), **AUTHORING_ERROR_RESPONSES},
        description=(
            f"Paginated authoring list of every Subject, drafts included. "
            f"{AUTHORING_PERMISSION}"
        ),
    ),
    post=extend_schema(
        request=SubjectWriteSerializer,
        responses={
            201: SubjectSerializer,
            200: SubjectSerializer,
            **AUTHORING_ERROR_RESPONSES,
        },
        description=(
            f"Create a Subject, or update the Subject owning the supplied "
            f"external_id (201 created, 200 updated). {AUTHORING_PERMISSION}"
        ),
    ),
)
class ContentSubjectListView(ContentListCreateView):
    model = Subject
    write_serializer_class = SubjectWriteSerializer
    read_serializer_class = SubjectSerializer

    def save_new(self, data, request):
        return upsert_subject(
            **data,
            external_id_provided="external_id" in request.data,
        )


@extend_schema_view(
    get=extend_schema(
        request=None,
        parameters=[CONTENT_PK_PARAMETER],
        responses={200: SubjectSerializer, **AUTHORING_ERROR_RESPONSES},
        description=f"Read one Subject. {AUTHORING_PERMISSION}",
    ),
    patch=extend_schema(
        request=SubjectWriteSerializer,
        parameters=[CONTENT_PK_PARAMETER],
        responses={200: SubjectSerializer, **AUTHORING_ERROR_RESPONSES},
        description=(
            f"Partially update one Subject; omitted fields keep their stored "
            f"values. {AUTHORING_PERMISSION}"
        ),
    ),
    delete=extend_schema(
        request=None,
        parameters=[CONTENT_PK_PARAMETER],
        responses={
            204: OpenApiResponse(description="The Subject was deleted."),
            **AUTHORING_ERROR_RESPONSES,
        },
        description=(
            f"Delete one Subject; a repeated DELETE is 404 "
            f"RESOURCE_NOT_FOUND. {AUTHORING_PERMISSION}"
        ),
    ),
)
class ContentSubjectDetailView(ContentDetailView):
    model = Subject
    write_serializer_class = SubjectWriteSerializer
    read_serializer_class = SubjectSerializer

    def update_existing(self, instance, data, request):
        subject, _ = upsert_subject(
            title=data.get("title", instance.title),
            description=data.get("description", instance.description),
            position=data.get("position"),
            external_id=data.get("external_id", instance.external_id),
            external_id_provided="external_id" in request.data,
            instance=instance,
        )
        return subject

    def delete_existing(self, instance, request):
        delete_subject(instance)


# --- sections ---------------------------------------------------------------


@extend_schema_view(
    get=extend_schema(
        request=None,
        responses={200: SectionSerializer(many=True), **AUTHORING_ERROR_RESPONSES},
        description=(
            f"Paginated authoring list of every Section, drafts included. "
            f"{AUTHORING_PERMISSION}"
        ),
    ),
    post=extend_schema(
        request=SectionWriteSerializer,
        responses={
            201: SectionSerializer,
            200: SectionSerializer,
            **AUTHORING_ERROR_RESPONSES,
        },
        description=(
            f"Create a Section under its subject, or update the Section owning "
            f"the supplied external_id (201 created, 200 updated). "
            f"{AUTHORING_PERMISSION}"
        ),
    ),
)
class ContentSectionListView(ContentListCreateView):
    model = Section
    write_serializer_class = SectionWriteSerializer
    read_serializer_class = SectionSerializer

    def save_new(self, data, request):
        subject, payload = _pop_relation(data, "subject")
        return upsert_section(
            subject,
            **payload,
            external_id_provided="external_id" in request.data,
        )


@extend_schema_view(
    get=extend_schema(
        request=None,
        parameters=[CONTENT_PK_PARAMETER],
        responses={200: SectionSerializer, **AUTHORING_ERROR_RESPONSES},
        description=f"Read one Section. {AUTHORING_PERMISSION}",
    ),
    patch=extend_schema(
        request=SectionWriteSerializer,
        parameters=[CONTENT_PK_PARAMETER],
        responses={200: SectionSerializer, **AUTHORING_ERROR_RESPONSES},
        description=(
            f"Partially update one Section; omitted fields keep their stored "
            f"values. {AUTHORING_PERMISSION}"
        ),
    ),
    delete=extend_schema(
        request=None,
        parameters=[CONTENT_PK_PARAMETER],
        responses={
            204: OpenApiResponse(description="The Section was deleted."),
            **AUTHORING_ERROR_RESPONSES,
        },
        description=(
            f"Delete one Section; a Section that still owns Topics is 409 "
            f"CONTENT_CONFLICT. {AUTHORING_PERMISSION}"
        ),
    ),
)
class ContentSectionDetailView(ContentDetailView):
    model = Section
    write_serializer_class = SectionWriteSerializer
    read_serializer_class = SectionSerializer

    def update_existing(self, instance, data, request):
        section, _ = upsert_section(
            data.get("subject", instance.subject),
            title=data.get("title", instance.title),
            description=data.get("description", instance.description),
            position=data.get("position"),
            external_id=data.get("external_id", instance.external_id),
            external_id_provided="external_id" in request.data,
            instance=instance,
        )
        return section

    def delete_existing(self, instance, request):
        delete_section(instance)


# --- topics -----------------------------------------------------------------


@extend_schema_view(
    get=extend_schema(
        request=None,
        responses={200: TopicSerializer(many=True), **AUTHORING_ERROR_RESPONSES},
        description=(
            f"Paginated authoring list of every Topic, drafts included. "
            f"{AUTHORING_PERMISSION}"
        ),
    ),
    post=extend_schema(
        request=TopicWriteSerializer,
        responses={
            201: TopicSerializer,
            200: TopicSerializer,
            **AUTHORING_ERROR_RESPONSES,
        },
        description=(
            f"Create a Topic under its section, or update the Topic owning the "
            f"supplied external_id (201 created, 200 updated). "
            f"{AUTHORING_PERMISSION}"
        ),
    ),
)
class ContentTopicListView(ContentListCreateView):
    model = Topic
    write_serializer_class = TopicWriteSerializer
    read_serializer_class = TopicSerializer

    def save_new(self, data, request):
        section, payload = _pop_relation(data, "section")
        return upsert_topic(
            section,
            **payload,
            external_id_provided="external_id" in request.data,
        )


@extend_schema_view(
    get=extend_schema(
        request=None,
        parameters=[CONTENT_PK_PARAMETER],
        responses={200: TopicSerializer, **AUTHORING_ERROR_RESPONSES},
        description=f"Read one Topic, including drafts. {AUTHORING_PERMISSION}",
    ),
    patch=extend_schema(
        request=TopicWriteSerializer,
        parameters=[CONTENT_PK_PARAMETER],
        responses={200: TopicSerializer, **AUTHORING_ERROR_RESPONSES},
        description=(
            f"Partially update one Topic; omitted fields keep their stored "
            f"values. {AUTHORING_PERMISSION}"
        ),
    ),
    delete=extend_schema(
        request=None,
        parameters=[CONTENT_PK_PARAMETER],
        responses={
            204: OpenApiResponse(
                description="The Topic and its owned children were deleted."
            ),
            **AUTHORING_ERROR_RESPONSES,
        },
        description=(
            f"Delete one Topic with its blocks, flashcards and quizzes; sibling "
            f"aggregates are untouched. {AUTHORING_PERMISSION}"
        ),
    ),
)
class ContentTopicDetailView(ContentDetailView):
    model = Topic
    write_serializer_class = TopicWriteSerializer
    read_serializer_class = TopicSerializer

    def update_existing(self, instance, data, request):
        topic, _ = upsert_topic(
            data.get("section", instance.section),
            title=data.get("title", instance.title),
            description=data.get("description", instance.description),
            position=data.get("position"),
            status=data.get("status", instance.status),
            access_level=data.get("access_level", instance.access_level),
            external_id=data.get("external_id", instance.external_id),
            external_id_provided="external_id" in request.data,
            instance=instance,
        )
        return topic

    def delete_existing(self, instance, request):
        delete_topic(instance)


# --- blocks -----------------------------------------------------------------


@extend_schema_view(
    get=extend_schema(
        request=None,
        responses={
            200: ContentBlockAuthoringSerializer(many=True),
            **AUTHORING_ERROR_RESPONSES,
        },
        description=(
            f"Paginated authoring list of every block with its raw body. "
            f"{AUTHORING_PERMISSION}"
        ),
    ),
    post=extend_schema(
        request=ContentBlockWriteSerializer,
        responses={
            201: ContentBlockAuthoringSerializer,
            200: ContentBlockAuthoringSerializer,
            **AUTHORING_ERROR_RESPONSES,
        },
        description=(
            f"Create a block under its topic, or update the block owning the "
            f"supplied external_id; block_type is addressed by key and the 002 "
            f"publish preconditions are re-checked. {AUTHORING_PERMISSION}"
        ),
    ),
)
class ContentBlockListView(ContentListCreateView):
    model = ContentBlock
    write_serializer_class = ContentBlockWriteSerializer
    read_serializer_class = ContentBlockAuthoringSerializer

    def save_new(self, data, request):
        topic, payload = _pop_relation(data, "topic")
        block_type = payload.pop("block_type")
        return upsert_content_block(
            topic,
            block_type_key=block_type.key,
            **payload,
            external_id_provided="external_id" in request.data,
        )


@extend_schema_view(
    get=extend_schema(
        request=None,
        parameters=[CONTENT_PK_PARAMETER],
        responses={
            200: ContentBlockAuthoringSerializer,
            **AUTHORING_ERROR_RESPONSES,
        },
        description=f"Read one block with its raw body. {AUTHORING_PERMISSION}",
    ),
    patch=extend_schema(
        request=ContentBlockWriteSerializer,
        parameters=[CONTENT_PK_PARAMETER],
        responses={
            200: ContentBlockAuthoringSerializer,
            **AUTHORING_ERROR_RESPONSES,
        },
        description=(
            f"Partially update one block; an omitted media key keeps the stored "
            f"reference and an explicit null clears it. {AUTHORING_PERMISSION}"
        ),
    ),
    delete=extend_schema(
        request=None,
        parameters=[CONTENT_PK_PARAMETER],
        responses={
            204: OpenApiResponse(description="The block was deleted."),
            **AUTHORING_ERROR_RESPONSES,
        },
        description=(
            f"Delete one block; a repeated DELETE is 404 RESOURCE_NOT_FOUND. "
            f"{AUTHORING_PERMISSION}"
        ),
    ),
)
class ContentBlockDetailView(ContentDetailView):
    model = ContentBlock
    write_serializer_class = ContentBlockWriteSerializer
    read_serializer_class = ContentBlockAuthoringSerializer

    def update_existing(self, instance, data, request):
        block_type = data.get("block_type", instance.block_type)
        block, _ = upsert_content_block(
            data.get("topic", instance.topic),
            block_type_key=block_type.key,
            markdown_body=data.get("markdown_body", instance.markdown_body),
            media=data.get("media", instance.media),
            caption=data.get("caption", instance.caption),
            position=data.get("position"),
            status=data.get("status", instance.status),
            is_demo_preview=data.get("is_demo_preview", instance.is_demo_preview),
            external_id=data.get("external_id", instance.external_id),
            external_id_provided="external_id" in request.data,
            instance=instance,
        )
        return block

    def delete_existing(self, instance, request):
        delete_content_block(instance)


# --- flashcards -------------------------------------------------------------


@extend_schema_view(
    get=extend_schema(
        request=None,
        responses={200: FlashcardSerializer(many=True), **AUTHORING_ERROR_RESPONSES},
        description=(
            f"Paginated authoring list of every Flashcard. {AUTHORING_PERMISSION}"
        ),
    ),
    post=extend_schema(
        request=FlashcardWriteSerializer,
        responses={
            201: FlashcardSerializer,
            200: FlashcardSerializer,
            **AUTHORING_ERROR_RESPONSES,
        },
        description=(
            f"Create a Flashcard under its topic, or update the Flashcard owning "
            f"the supplied external_id (201 created, 200 updated). "
            f"{AUTHORING_PERMISSION}"
        ),
    ),
)
class ContentFlashcardListView(ContentListCreateView):
    model = Flashcard
    write_serializer_class = FlashcardWriteSerializer
    read_serializer_class = FlashcardSerializer

    def save_new(self, data, request):
        topic, payload = _pop_relation(data, "topic")
        return upsert_flashcard(
            topic,
            **payload,
            external_id_provided="external_id" in request.data,
        )


@extend_schema_view(
    get=extend_schema(
        request=None,
        parameters=[CONTENT_PK_PARAMETER],
        responses={200: FlashcardSerializer, **AUTHORING_ERROR_RESPONSES},
        description=f"Read one Flashcard. {AUTHORING_PERMISSION}",
    ),
    patch=extend_schema(
        request=FlashcardWriteSerializer,
        parameters=[CONTENT_PK_PARAMETER],
        responses={200: FlashcardSerializer, **AUTHORING_ERROR_RESPONSES},
        description=(
            f"Partially update one Flashcard; omitted fields keep their stored "
            f"values. {AUTHORING_PERMISSION}"
        ),
    ),
    delete=extend_schema(
        request=None,
        parameters=[CONTENT_PK_PARAMETER],
        responses={
            204: OpenApiResponse(description="The Flashcard was deleted."),
            **AUTHORING_ERROR_RESPONSES,
        },
        description=(
            f"Delete one Flashcard, leaving Source links behind. {AUTHORING_PERMISSION}"
        ),
    ),
)
class ContentFlashcardDetailView(ContentDetailView):
    model = Flashcard
    write_serializer_class = FlashcardWriteSerializer
    read_serializer_class = FlashcardSerializer

    def update_existing(self, instance, data, request):
        flashcard, _ = upsert_flashcard(
            data.get("topic", instance.topic),
            question=data.get("question", instance.question),
            answer=data.get("answer", instance.answer),
            position=data.get("position"),
            external_id=data.get("external_id", instance.external_id),
            external_id_provided="external_id" in request.data,
            instance=instance,
        )
        return flashcard

    def delete_existing(self, instance, request):
        delete_flashcard(instance)


# --- quizzes ----------------------------------------------------------------


@extend_schema_view(
    get=extend_schema(
        request=None,
        responses={200: QuizSerializer(many=True), **AUTHORING_ERROR_RESPONSES},
        description=(
            f"Paginated authoring list of every Quiz with scalar fields only. "
            f"{AUTHORING_PERMISSION}"
        ),
    ),
    post=extend_schema(
        request=QuizWriteSerializer,
        responses={
            201: QuizSerializer,
            200: QuizSerializer,
            **AUTHORING_ERROR_RESPONSES,
        },
        description=(
            f"Create a Quiz aggregate with nested questions and answers, or "
            f"update the Quiz owning the supplied external_id (201 created, 200 "
            f"updated); the nested questions are returned by the detail read. "
            f"{AUTHORING_PERMISSION}"
        ),
    ),
)
class ContentQuizListView(ContentListCreateView):
    model = Quiz
    write_serializer_class = QuizWriteSerializer
    read_serializer_class = QuizSerializer

    def save_new(self, data, request):
        topic, payload = _pop_relation(data, "topic")
        return upsert_quiz(
            topic,
            **payload,
            external_id_provided="external_id" in request.data,
        )


@extend_schema_view(
    get=extend_schema(
        request=None,
        parameters=[CONTENT_PK_PARAMETER],
        responses={200: QuizDetailSerializer, **AUTHORING_ERROR_RESPONSES},
        description=(
            f"Read one Quiz with its nested questions and answers. "
            f"{AUTHORING_PERMISSION}"
        ),
    ),
    patch=extend_schema(
        request=QuizWriteSerializer,
        parameters=[CONTENT_PK_PARAMETER],
        responses={200: QuizDetailSerializer, **AUTHORING_ERROR_RESPONSES},
        description=(
            f"Partially update one Quiz; nested items carrying an id are "
            f"updated in place and an omitted questions key keeps the "
            f"aggregate. {AUTHORING_PERMISSION}"
        ),
    ),
    delete=extend_schema(
        request=None,
        parameters=[CONTENT_PK_PARAMETER],
        responses={
            204: OpenApiResponse(
                description="The Quiz with its questions and answers was deleted."
            ),
            **AUTHORING_ERROR_RESPONSES,
        },
        description=(
            f"Delete one Quiz with its questions and answers; a repeated DELETE "
            f"is 404 RESOURCE_NOT_FOUND. {AUTHORING_PERMISSION}"
        ),
    ),
)
class ContentQuizDetailView(ContentDetailView):
    model = Quiz
    write_serializer_class = QuizWriteSerializer
    read_serializer_class = QuizSerializer
    detail_serializer_class = QuizDetailSerializer

    def update_existing(self, instance, data, request):
        quiz, _ = upsert_quiz(
            data.get("topic", instance.topic),
            title=data.get("title", instance.title),
            description=data.get("description", instance.description),
            position=data.get("position"),
            questions=data.get("questions"),
            external_id=data.get("external_id", instance.external_id),
            external_id_provided="external_id" in request.data,
            instance=instance,
        )
        return quiz

    def delete_existing(self, instance, request):
        delete_quiz(instance)


# --- sources ----------------------------------------------------------------


@extend_schema_view(
    get=extend_schema(
        request=None,
        responses={
            200: SourceAuthoringSerializer(many=True),
            **AUTHORING_ERROR_RESPONSES,
        },
        description=(
            f"Paginated authoring list of every Source with its relation ids. "
            f"{AUTHORING_PERMISSION}"
        ),
    ),
    post=extend_schema(
        request=SourceWriteSerializer,
        responses={
            201: SourceAuthoringSerializer,
            200: SourceAuthoringSerializer,
            **AUTHORING_ERROR_RESPONSES,
        },
        description=(
            f"Create a Source, or update the Source owning the supplied "
            f"external_id; every id list is the complete relation set of its "
            f"field. {AUTHORING_PERMISSION}"
        ),
    ),
)
class ContentSourceListView(ContentListCreateView):
    model = Source
    write_serializer_class = SourceWriteSerializer
    read_serializer_class = SourceAuthoringSerializer

    def save_new(self, data, request):
        return upsert_source(
            **data,
            external_id_provided="external_id" in request.data,
        )


@extend_schema_view(
    get=extend_schema(
        request=None,
        parameters=[CONTENT_PK_PARAMETER],
        responses={200: SourceAuthoringSerializer, **AUTHORING_ERROR_RESPONSES},
        description=(f"Read one Source with its relation ids. {AUTHORING_PERMISSION}"),
    ),
    patch=extend_schema(
        request=SourceWriteSerializer,
        parameters=[CONTENT_PK_PARAMETER],
        responses={200: SourceAuthoringSerializer, **AUTHORING_ERROR_RESPONSES},
        description=(
            f"Partially update one Source; omitted or null id lists keep the "
            f"stored relations. {AUTHORING_PERMISSION}"
        ),
    ),
    delete=extend_schema(
        request=None,
        parameters=[CONTENT_PK_PARAMETER],
        responses={
            204: OpenApiResponse(
                description="The Source was deleted; content is untouched."
            ),
            **AUTHORING_ERROR_RESPONSES,
        },
        description=(
            f"Delete one Source, removing its links only. {AUTHORING_PERMISSION}"
        ),
    ),
)
class ContentSourceDetailView(ContentDetailView):
    model = Source
    write_serializer_class = SourceWriteSerializer
    read_serializer_class = SourceAuthoringSerializer

    def update_existing(self, instance, data, request):
        source, _ = upsert_source(
            title=data.get("title", instance.title),
            source_type=data.get("source_type", instance.source_type),
            author=data.get("author", instance.author),
            year=data.get("year", instance.year),
            url=data.get("url", instance.url),
            note=data.get("note", instance.note),
            topic_ids=data.get("topic_ids"),
            block_ids=data.get("block_ids"),
            flashcard_ids=data.get("flashcard_ids"),
            question_ids=data.get("question_ids"),
            external_id=data.get("external_id", instance.external_id),
            external_id_provided="external_id" in request.data,
            instance=instance,
        )
        return source

    def delete_existing(self, instance, request):
        delete_source(instance)
