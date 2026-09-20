from django.urls import path

from .views import (
    LogoutAllView,
    LogoutView,
    MeView,
    ProfileView,
    RefreshTokenView,
    TelegramLoginView,
)

urlpatterns = [
    path("auth/telegram/", TelegramLoginView.as_view(), name="auth-telegram"),
    path(
        "auth/token/refresh/",
        RefreshTokenView.as_view(),
        name="auth-token-refresh",
    ),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("auth/logout-all/", LogoutAllView.as_view(), name="auth-logout-all"),
    path("auth/me/", MeView.as_view(), name="auth-me"),
    path("profile/", ProfileView.as_view(), name="user-profile"),
]
