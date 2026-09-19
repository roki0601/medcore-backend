from __future__ import annotations

import pytest
from django.contrib.auth.models import AnonymousUser
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from apps.common.exceptions import APIError
from apps.common.integration import (
    INTEGRATION_KEY_HEADER,
    HasIntegrationKey,
    IntegrationClient,
    IntegrationKeyAuthentication,
)
from apps.common.permissions import (
    CONTENT_AUTHOR_ROLES,
    IsContentAuthor,
    IsNotIntegrationClient,
)
from apps.users.models import User

INTEGRATION_KEY = "unit-test-integration-key"
HEADER_KWARG = f"HTTP_{INTEGRATION_KEY_HEADER.upper().replace('-', '_')}"

factory = APIRequestFactory()
authentication = IntegrationKeyAuthentication()


def build_request(**headers) -> Request:
    return Request(factory.get("/", **headers))


def make_user(**attributes) -> User:
    """Build an unsaved user; the permission classes only read attributes."""

    return User(**attributes)


def test_correct_key_authenticates_the_integration_client(settings):
    settings.MEDCORE_CONTENT_API_KEY = INTEGRATION_KEY

    principal, auth = authentication.authenticate(
        build_request(**{HEADER_KWARG: INTEGRATION_KEY})
    )

    assert isinstance(auth, IntegrationClient)
    assert isinstance(principal, AnonymousUser)
    assert principal.is_authenticated is False


def test_integration_principal_is_not_a_user(settings):
    settings.MEDCORE_CONTENT_API_KEY = INTEGRATION_KEY

    _, auth = authentication.authenticate(
        build_request(**{HEADER_KWARG: INTEGRATION_KEY})
    )

    assert not isinstance(auth, User)
    assert not hasattr(auth, "role")
    assert not hasattr(auth, "is_authenticated")
    assert not hasattr(auth, "is_superuser")
    assert not hasattr(auth, "pk")


def test_wrong_key_is_rejected(settings):
    settings.MEDCORE_CONTENT_API_KEY = INTEGRATION_KEY

    with pytest.raises(APIError) as excinfo:
        authentication.authenticate(build_request(**{HEADER_KWARG: "not-the-key"}))

    assert excinfo.value.default_code == "INTEGRATION_KEY_INVALID"
    assert excinfo.value.status_code == 401


@pytest.mark.parametrize("configured", ["", None])
def test_empty_configured_key_denies_every_request(settings, configured):
    settings.MEDCORE_CONTENT_API_KEY = configured

    with pytest.raises(APIError) as excinfo:
        authentication.authenticate(build_request(**{HEADER_KWARG: ""}))

    assert excinfo.value.default_code == "INTEGRATION_KEY_INVALID"
    assert excinfo.value.status_code == 401


def test_empty_configured_key_denies_a_previously_valid_looking_key(settings):
    settings.MEDCORE_CONTENT_API_KEY = ""

    with pytest.raises(APIError) as excinfo:
        authentication.authenticate(build_request(**{HEADER_KWARG: INTEGRATION_KEY}))

    assert excinfo.value.default_code == "INTEGRATION_KEY_INVALID"


def test_absent_header_falls_through_to_the_next_authenticator(settings):
    settings.MEDCORE_CONTENT_API_KEY = INTEGRATION_KEY

    assert authentication.authenticate(build_request()) is None


def test_has_integration_key_only_accepts_the_integration_principal():
    permission = HasIntegrationKey()

    assert permission.has_permission(build_request(), None) is False

    request = build_request()
    request.auth = IntegrationClient()
    assert permission.has_permission(request, None) is True

    request.auth = None
    assert permission.has_permission(request, None) is False


def test_content_author_roles_are_the_editor_and_admin_roles():
    assert CONTENT_AUTHOR_ROLES == {User.Role.EDITOR, User.Role.ADMIN}


@pytest.mark.parametrize("role", [User.Role.EDITOR, User.Role.ADMIN])
def test_content_author_accepts_active_editor_and_admin(role):
    request = build_request()
    request.user = make_user(username="author", role=role, is_active=True)

    assert IsContentAuthor().has_permission(request, None) is True


def test_content_author_accepts_an_active_superuser():
    request = build_request()
    request.user = make_user(
        username="root", role=User.Role.USER, is_active=True, is_superuser=True
    )

    assert IsContentAuthor().has_permission(request, None) is True


@pytest.mark.parametrize(
    "attributes",
    [
        {"username": "reader", "role": User.Role.USER, "is_active": True},
        {"username": "inactive", "role": User.Role.EDITOR, "is_active": False},
    ],
)
def test_content_author_rejects_plain_and_inactive_users(attributes):
    request = build_request()
    request.user = make_user(**attributes)

    assert IsContentAuthor().has_permission(request, None) is False


def test_content_author_rejects_the_integration_principal():
    request = build_request()
    request.user = AnonymousUser()
    request.auth = IntegrationClient()

    assert IsContentAuthor().has_permission(request, None) is False


def test_not_integration_client_rejects_the_integration_principal():
    request = build_request()
    request.auth = IntegrationClient()

    with pytest.raises(APIError) as excinfo:
        IsNotIntegrationClient().has_permission(request, None)

    assert excinfo.value.default_code == "INTEGRATION_SCOPE_FORBIDDEN"
    assert excinfo.value.status_code == 403


@pytest.mark.parametrize("auth", [None, "user-jwt"])
def test_not_integration_client_allows_other_principals(auth):
    request = build_request()
    request.auth = auth

    assert IsNotIntegrationClient().has_permission(request, None) is True
