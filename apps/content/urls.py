from django.urls import path

from .views import (
    ContentBlockDetailView,
    ContentBlockListView,
    ContentFlashcardDetailView,
    ContentFlashcardListView,
    ContentQuizDetailView,
    ContentQuizListView,
    ContentSectionDetailView,
    ContentSectionListView,
    ContentSourceDetailView,
    ContentSourceListView,
    ContentSubjectDetailView,
    ContentSubjectListView,
    ContentTopicDetailView,
    ContentTopicListView,
    PublicSitemapView,
    SearchView,
    SectionDetailView,
    SubjectBySlugView,
    SubjectDetailView,
    SubjectListView,
    TopicBySlugView,
    TopicContentView,
    TopicDetailView,
    TopicListView,
)

urlpatterns = [
    path("subjects/", SubjectListView.as_view(), name="subject-list"),
    path(
        "subjects/by-slug/<slug:slug>/",
        SubjectBySlugView.as_view(),
        name="subject-by-slug",
    ),
    path("subjects/<int:pk>/", SubjectDetailView.as_view(), name="subject-detail"),
    path("sections/<int:pk>/", SectionDetailView.as_view(), name="section-detail"),
    path("topics/", TopicListView.as_view(), name="topic-list"),
    path(
        "topics/by-slug/<slug:subject_slug>/<slug:topic_slug>/",
        TopicBySlugView.as_view(),
        name="topic-by-slug",
    ),
    path("topics/<int:pk>/", TopicDetailView.as_view(), name="topic-detail"),
    path("catalog/sitemap/", PublicSitemapView.as_view(), name="public-sitemap"),
    path(
        "topics/<int:pk>/content/",
        TopicContentView.as_view(),
        name="topic-content",
    ),
    path("search/", SearchView.as_view(), name="search"),
    path(
        "content/subjects/",
        ContentSubjectListView.as_view(),
        name="content-subject-list",
    ),
    path(
        "content/subjects/<int:pk>/",
        ContentSubjectDetailView.as_view(),
        name="content-subject-detail",
    ),
    path(
        "content/sections/",
        ContentSectionListView.as_view(),
        name="content-section-list",
    ),
    path(
        "content/sections/<int:pk>/",
        ContentSectionDetailView.as_view(),
        name="content-section-detail",
    ),
    path(
        "content/topics/",
        ContentTopicListView.as_view(),
        name="content-topic-list",
    ),
    path(
        "content/topics/<int:pk>/",
        ContentTopicDetailView.as_view(),
        name="content-topic-detail",
    ),
    path(
        "content/blocks/",
        ContentBlockListView.as_view(),
        name="content-block-list",
    ),
    path(
        "content/blocks/<int:pk>/",
        ContentBlockDetailView.as_view(),
        name="content-block-detail",
    ),
    path(
        "content/flashcards/",
        ContentFlashcardListView.as_view(),
        name="content-flashcard-list",
    ),
    path(
        "content/flashcards/<int:pk>/",
        ContentFlashcardDetailView.as_view(),
        name="content-flashcard-detail",
    ),
    path(
        "content/quizzes/",
        ContentQuizListView.as_view(),
        name="content-quiz-list",
    ),
    path(
        "content/quizzes/<int:pk>/",
        ContentQuizDetailView.as_view(),
        name="content-quiz-detail",
    ),
    path(
        "content/sources/",
        ContentSourceListView.as_view(),
        name="content-source-list",
    ),
    path(
        "content/sources/<int:pk>/",
        ContentSourceDetailView.as_view(),
        name="content-source-detail",
    ),
]
