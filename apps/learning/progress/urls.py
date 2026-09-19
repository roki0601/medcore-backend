"""URLs for the topic progress sub-domain (owned by the `Z2-progress` zone)."""

from django.urls import path

from apps.learning.progress.views import (
    TopicBlockCompleteView,
    TopicProgressView,
)

urlpatterns = [
    path(
        "topics/<int:topic_id>/progress/",
        TopicProgressView.as_view(),
        name="learning-topic-progress",
    ),
    path(
        "topics/<int:topic_id>/blocks/<int:block_id>/complete/",
        TopicBlockCompleteView.as_view(),
        name="learning-topic-block-complete",
    ),
]
