from django.urls import include, path

urlpatterns = [
    path("", include("apps.learning.dashboard.urls")),
    path("", include("apps.learning.progress.urls")),
    path("", include("apps.learning.flashcards.urls")),
    path("", include("apps.learning.quizzes.urls")),
]
