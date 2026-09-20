from django.urls import path

from .views import csrf_token, health, health_live, health_ready

urlpatterns = [
    path("health/", health, name="health"),
    path("health/live/", health_live, name="health-live"),
    path("health/ready/", health_ready, name="health-ready"),
    path("auth/csrf/", csrf_token, name="auth-csrf"),
]
