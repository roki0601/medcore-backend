"""URLs for the flashcard review sub-domain (owned by the `Z3-flashcards` zone)."""

from django.urls import path

from apps.learning.flashcards import views

urlpatterns = [
    path(
        "topics/<int:topic_id>/flashcards/",
        views.TopicFlashcardListView.as_view(),
        name="learning-topic-flashcards",
    ),
    path(
        "flashcards/review-due/",
        views.FlashcardReviewDueView.as_view(),
        name="learning-flashcard-review-due",
    ),
    path(
        "flashcards/<int:pk>/",
        views.FlashcardDetailView.as_view(),
        name="learning-flashcard-detail",
    ),
    path(
        "flashcards/<int:pk>/review/",
        views.FlashcardReviewView.as_view(),
        name="learning-flashcard-review",
    ),
]
