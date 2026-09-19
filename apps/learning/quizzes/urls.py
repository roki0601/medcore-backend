"""URLs for the quiz and quiz-attempt sub-domain (owned by the `Z4-quizzes` zone)."""

from django.urls import path

from apps.learning.quizzes.views import (
    QuizAttemptDetailView,
    QuizAttemptStartView,
    QuizAttemptSubmitView,
    QuizDetailView,
    TopicQuizListView,
)

urlpatterns = [
    path(
        "topics/<int:topic_id>/quizzes/",
        TopicQuizListView.as_view(),
        name="learning-topic-quizzes",
    ),
    path(
        "quizzes/<int:pk>/",
        QuizDetailView.as_view(),
        name="learning-quiz-detail",
    ),
    path(
        "quizzes/<int:pk>/attempts/",
        QuizAttemptStartView.as_view(),
        name="learning-quiz-attempt-start",
    ),
    path(
        "quiz-attempts/<int:pk>/",
        QuizAttemptDetailView.as_view(),
        name="learning-quiz-attempt-detail",
    ),
    path(
        "quiz-attempts/<int:pk>/submit/",
        QuizAttemptSubmitView.as_view(),
        name="learning-quiz-attempt-submit",
    ),
]
