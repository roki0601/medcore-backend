"""HTTP layer for topic progress and theory-block completion (feature 003)."""

from __future__ import annotations

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.learning.access import get_accessible_published_topic
from apps.learning.models import UserTopicProgress
from apps.learning.progress.selectors import build_topic_progress_snapshot
from apps.learning.progress.serializers import (
    TopicProgressSerializer,
    TopicProgressUpdateSerializer,
)
from apps.learning.progress.services import (
    complete_topic_block,
    mark_topic_learned,
    open_topic,
)
from apps.learning.serializers import EmptyBodySerializer

ERROR_RESPONSES = {
    401: OpenApiResponse(
        description="Authentication required (AUTHENTICATION_REQUIRED)."
    ),
    403: OpenApiResponse(
        description="Paid-topic entitlement required (TOPIC_ENTITLEMENT_REQUIRED)."
    ),
    404: OpenApiResponse(description="Resource not found (RESOURCE_NOT_FOUND)."),
    422: OpenApiResponse(description="Request validation failed (VALIDATION_ERROR)."),
    429: OpenApiResponse(description="Too many requests (THROTTLED)."),
}


class TopicProgressView(generics.GenericAPIView):
    """The user's derived progress snapshot; ``GET`` reads, ``PATCH`` transitions."""

    permission_classes = (IsAuthenticated,)
    serializer_class = TopicProgressSerializer

    def get_throttles(self):
        """Reads use ``learning_read``; ``PATCH`` uses ``learning_progress``."""

        self.throttle_scope = (
            "learning_read" if self.request.method == "GET" else "learning_progress"
        )
        return super().get_throttles()

    @extend_schema(
        request=None,
        responses={200: TopicProgressSerializer, **ERROR_RESPONSES},
        description=(
            "Derived theory progress for one accessible topic. Reads only: a "
            "never-touched topic reports not_started with null timestamps. "
            "Throttle scope: learning_read."
        ),
    )
    def get(self, request, topic_id: int):
        topic = get_accessible_published_topic(topic_id, request.user)
        snapshot = build_topic_progress_snapshot(request.user, topic)
        return Response(self.get_serializer(snapshot).data)

    @extend_schema(
        request=TopicProgressUpdateSerializer,
        responses={200: TopicProgressSerializer, **ERROR_RESPONSES},
        description=(
            'Open the topic ({"opened": true} stamps last_opened_at and moves a '
            "new row to learning) and/or apply the explicit manual transition "
            '({"status": "learned"}, which never regresses). Throttle scope: '
            "learning_progress."
        ),
    )
    def patch(self, request, topic_id: int):
        topic = get_accessible_published_topic(topic_id, request.user)
        serializer = TopicProgressUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        if payload.get("opened"):
            open_topic(request.user, topic)
        if payload.get("status") == UserTopicProgress.Status.LEARNED:
            mark_topic_learned(request.user, topic)
        snapshot = build_topic_progress_snapshot(request.user, topic)
        return Response(self.get_serializer(snapshot).data)


class TopicBlockCompleteView(generics.GenericAPIView):
    """Explicit completion of one published theory block of a topic."""

    permission_classes = (IsAuthenticated,)
    throttle_scope = "learning_progress"
    serializer_class = TopicProgressSerializer

    @extend_schema(
        request=None,
        responses={
            201: TopicProgressSerializer,
            200: TopicProgressSerializer,
            **ERROR_RESPONSES,
        },
        description=(
            "Mark a published block of the URL topic complete (201 first time, "
            "200 on an idempotent repeat) and return the derived progress. The "
            "topic is resolved from the block; a block of another topic or an "
            "unpublished block is RESOURCE_NOT_FOUND. Throttle scope: "
            "learning_progress."
        ),
    )
    def post(self, request, topic_id: int, block_id: int):
        topic = get_accessible_published_topic(topic_id, request.user)
        EmptyBodySerializer(data=request.data).is_valid(raise_exception=True)
        _, created = complete_topic_block(request.user, topic, block_id)
        snapshot = build_topic_progress_snapshot(request.user, topic)
        return Response(
            self.get_serializer(snapshot).data,
            status=201 if created else 200,
        )
