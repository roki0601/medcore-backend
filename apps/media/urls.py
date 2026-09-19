from django.urls import path

from .views import (
    MediaAccessUrlView,
    MediaDetailView,
    MediaFileDownloadView,
    MediaListCreateView,
    MediaUploadReceiverView,
    MediaUploadUrlView,
)

#: The two controlled endpoints come before the numeric detail route so the
#: token paths can never be read as a media id.
urlpatterns = [
    path("media/", MediaListCreateView.as_view(), name="media-list"),
    path(
        "media/upload/<str:token>/",
        MediaUploadReceiverView.as_view(),
        name="media-upload",
    ),
    path(
        "media/file/<str:token>/",
        MediaFileDownloadView.as_view(),
        name="media-file",
    ),
    path("media/<int:pk>/", MediaDetailView.as_view(), name="media-detail"),
    path(
        "media/<int:pk>/upload-url/",
        MediaUploadUrlView.as_view(),
        name="media-upload-url",
    ),
    path(
        "media/<int:pk>/access-url/",
        MediaAccessUrlView.as_view(),
        name="media-access-url",
    ),
]
