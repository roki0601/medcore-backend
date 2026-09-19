from __future__ import annotations

from rest_framework.permissions import BasePermission

from apps.common.exceptions import APIError
from apps.common.integration import IntegrationClient

#: Application roles allowed to author content through the CMS and the API.
#: ``User.Role.EDITOR``/``User.Role.ADMIN`` carry exactly these string values.
CONTENT_AUTHOR_ROLES = frozenset({"editor", "admin"})


class IsContentAuthor(BasePermission):
    """Allow an active user holding an editor/admin role (or a superuser).

    The integration principal is an ``AnonymousUser``, so it never satisfies
    this permission; integration routes combine it with ``HasIntegrationKey``
    instead of widening this role check.
    """

    def has_permission(self, request, view) -> bool:
        user = request.user
        if user is None or not user.is_authenticated or not user.is_active:
            return False
        return bool(
            user.is_superuser or getattr(user, "role", None) in CONTENT_AUTHOR_ROLES
        )


class IsNotIntegrationClient(BasePermission):
    """Reject the integration principal on routes outside its scope.

    User-facing and read-authorization routes (for example the protected media
    ``access-url``) must not be reachable with the integration key, so a
    request authenticated as an :class:`~apps.common.integration.IntegrationClient`
    is refused with a stable 403 instead of silently passing as anonymous.
    """

    def has_permission(self, request, view) -> bool:
        if isinstance(request.auth, IntegrationClient):
            raise APIError(
                "The integration key cannot be used for this operation.",
                code="INTEGRATION_SCOPE_FORBIDDEN",
                status_code=403,
            )
        return True
