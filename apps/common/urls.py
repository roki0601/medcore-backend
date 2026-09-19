from django.urls import path

from .views import csrf_token, health

urlpatterns = [
    path("health/", health, name="health"),
    path("auth/csrf/", csrf_token, name="auth-csrf"),
]
