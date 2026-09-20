"""Flashcard routes of the learning API (feature 003).

Every view requires an authenticated user, re-resolves the published Topic and
the ``content`` access decision, and throttles reads and writes separately.
"""

from __future__ import annotations

from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.common.serializers import APIErrorResponseSerializer
from apps.learning.access import (
    get_accessible_flashcard,
    get_accessible_published_topic,
)
from apps.learning.flashcards.selectors import (
    due_flashcard_reviews,
    reviews_by_flashcard,
    topic_flashcards,
)
from apps.learning.flashcards.serializers import (
    DueFlashcardSerializer,
    FlashcardItemSerializer,
    FlashcardReviewRequestSerializer,
)
from apps.learning.flashcards.services import review_flashcard

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
        response=APIErrorResponseSerializer, description="Request validation failed."
    ),
    429: OpenApiResponse(
        response=APIErrorResponseSerializer, description="Too many requests."
    ),
}

AUTHENTICATED_PERMISSION = "Permission: authenticated user JWT."


class TopicFlashcardListView(generics.GenericAPIView):
    permission_classes = (IsAuthenticated,)
    throttle_scope = "learning_read"
    serializer_class = FlashcardItemSerializer

    @extend_schema(
        responses={200: FlashcardItemSerializer(many=True), **ERROR_RESPONSES},
        description=(
            "Paginated flashcards of an accessible published Topic in "
            "(position, id) order, each with the current user's review state "
            "(`review` is null when the card was never reviewed). "
            f"{AUTHENTICATED_PERMISSION}"
        ),
    )
    def get(self, request, topic_id: int):
        topic = get_accessible_published_topic(topic_id, request.user)
        flashcards = list(topic_flashcards(topic))
        reviews = reviews_by_flashcard(request.user, [card.pk for card in flashcards])
        page = self.paginate_queryset(flashcards)
        return self.get_paginated_response(
            self.get_serializer(page, many=True, context={"reviews": reviews}).data
        )


class FlashcardDetailView(generics.GenericAPIView):
    permission_classes = (IsAuthenticated,)
    throttle_scope = "learning_read"
    serializer_class = FlashcardItemSerializer

    @extend_schema(
        responses={200: FlashcardItemSerializer, **ERROR_RESPONSES},
        description=(
            "One flashcard of an accessible published Topic with the current "
            f"user's review state. {AUTHENTICATED_PERMISSION}"
        ),
    )
    def get(self, request, pk: int):
        flashcard = get_accessible_flashcard(pk, request.user)
        reviews = reviews_by_flashcard(request.user, [flashcard.pk])
        return Response(
            self.get_serializer(flashcard, context={"reviews": reviews}).data
        )


class FlashcardReviewDueView(generics.GenericAPIView):
    permission_classes = (IsAuthenticated,)
    throttle_scope = "learning_read"
    serializer_class = DueFlashcardSerializer

    @extend_schema(
        responses={200: DueFlashcardSerializer(many=True), **ERROR_RESPONSES},
        description=(
            "Paginated cards due for review: the current user's review rows with "
            "next_review_at <= now on published, accessible Topics, ordered by "
            f"(next_review_at, id). {AUTHENTICATED_PERMISSION}"
        ),
    )
    def get(self, request):
        reviews = due_flashcard_reviews(request.user, now=timezone.now())
        page = self.paginate_queryset(reviews)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)


class FlashcardReviewView(generics.GenericAPIView):
    permission_classes = (IsAuthenticated,)
    throttle_scope = "learning_review"
    serializer_class = FlashcardReviewRequestSerializer

    @extend_schema(
        request=FlashcardReviewRequestSerializer,
        responses={
            201: FlashcardItemSerializer,
            200: FlashcardItemSerializer,
            **ERROR_RESPONSES,
        },
        description=(
            "Record one review action (`know` advances one interval, `repeat` "
            "resets to the first). One current row per user/card: 201 on create, "
            "200 on update; the Topic progress moves to `learning` in the same "
            f"transaction. {AUTHENTICATED_PERMISSION}"
        ),
    )
    def post(self, request, pk: int):
        flashcard = get_accessible_flashcard(pk, request.user)
        serializer = FlashcardReviewRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        review, created = review_flashcard(
            request.user,
            flashcard,
            action=serializer.validated_data["action"],
        )
        payload = FlashcardItemSerializer(
            flashcard,
            context={"reviews": {flashcard.pk: review}},
        )
        return Response(payload.data, status=201 if created else 200)
