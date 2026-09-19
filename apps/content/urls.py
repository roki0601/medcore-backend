from django.urls import path

from .views import (
    SearchView,
    SectionDetailView,
    SubjectDetailView,
    SubjectListView,
    TopicContentView,
    TopicDetailView,
    TopicListView,
)

urlpatterns = [
    path("subjects/", SubjectListView.as_view(), name="subject-list"),
    path("subjects/<int:pk>/", SubjectDetailView.as_view(), name="subject-detail"),
    path("sections/<int:pk>/", SectionDetailView.as_view(), name="section-detail"),
    path("topics/", TopicListView.as_view(), name="topic-list"),
    path("topics/<int:pk>/", TopicDetailView.as_view(), name="topic-detail"),
    path(
        "topics/<int:pk>/content/",
        TopicContentView.as_view(),
        name="topic-content",
    ),
    path("search/", SearchView.as_view(), name="search"),
]
