from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.permissions import AllowAny, IsAdminUser

schema_permissions = [AllowAny] if settings.OPENAPI_PUBLIC else [IsAdminUser]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("apps.common.urls")),
    path("api/v1/", include("apps.users.urls")),
    path("api/v1/", include("apps.content.urls")),
    path("api/v1/", include("apps.learning.urls")),
    path("api/v1/", include("apps.media.urls")),
    path(
        "api/v1/schema/",
        SpectacularAPIView.as_view(permission_classes=schema_permissions),
        name="schema",
    ),
    path(
        "api/v1/docs/",
        SpectacularSwaggerView.as_view(
            url_name="schema",
            permission_classes=schema_permissions,
        ),
        name="swagger-ui",
    ),
]
