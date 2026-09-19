from __future__ import annotations

import secrets
from dataclasses import dataclass

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from rest_framework.authentication import BaseAuthentication
from rest_framework.permissions import BasePermission

from apps.common.exceptions import APIError

INTEGRATION_KEY_HEADER = "X-MedCore-Integration-Key"
INTEGRATION_KEY_META = "HTTP_X_MEDCORE_INTEGRATION_KEY"


@dataclass(frozen=True)
class IntegrationClient:
    """The authenticated principal of a request carrying the integration key.

    It deliberately carries no state at all. The integration client is *not* a
    ``User`` and must never be turned into one: it has no Django user
    attributes, no application ``role`` and no database row, so it cannot
    satisfy ``IsAuthenticated``, cannot be granted user-facing endpoints, cannot
    be checked against the editor/admin content roles and cannot bypass Topic
    access policy. Only the two explicit content/media scope permissions
    (``HasIntegrationKey`` and ``IsContentAuthor``) accept it.
    """


def _key_matches(provided: str, configured: str) -> bool:
    """Compare two secrets in constant time.

    A byte-wise early-exit comparison would leak the configured key one byte at
    a time through response timing, so the comparison always inspects every
    byte. ``secrets.compare_digest`` is used on encoded bytes so that a
    non-ASCII header value is a plain mismatch instead of an exception.
    """

    return secrets.compare_digest(provided.encode("utf-8"), configured.encode("utf-8"))


class IntegrationKeyAuthentication(BaseAuthentication):
    """Authenticate the external content client through the integration header.

    This authenticator is attached only to explicitly marked content/media
    routes and runs before the JWT authenticator there:

    - header absent -> ``None``, so DRF falls through to the normal JWT path;
    - header present but the configured key is unset/empty -> hard failure
      (an unset ``MEDCORE_CONTENT_API_KEY`` denies every integration request);
    - header present but wrong -> hard failure, even when a valid user JWT is
      supplied alongside it;
    - header present and correct -> ``(AnonymousUser(), IntegrationClient())``.

    The raw key is never logged and never persisted.
    """

    def authenticate_header(self, request) -> str:
        """Advertise the auth challenge for the marked content/media routes.

        DRF answers an unauthenticated request with 403 instead of 401 when the
        first authenticator advertises no challenge, and the integration key is
        a plain header rather than a challenge scheme. These routes must answer
        401 ``AUTHENTICATION_REQUIRED``, so the challenge names the Bearer
        credential that is the alternative on them; the integration key still
        travels in its own header.
        """

        return 'Bearer realm="api"'

    def authenticate(self, request):
        provided = request.META.get(INTEGRATION_KEY_META)
        if provided is None:
            return None

        configured = settings.MEDCORE_CONTENT_API_KEY or ""
        if not configured or not _key_matches(provided, configured):
            raise APIError(
                "The integration key is invalid.",
                code="INTEGRATION_KEY_INVALID",
                status_code=401,
            )

        return (AnonymousUser(), IntegrationClient())


class HasIntegrationKey(BasePermission):
    """Allow the request only when it was authenticated by the integration key."""

    def has_permission(self, request, view) -> bool:
        return isinstance(request.auth, IntegrationClient)
