import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.users.models import RefreshSession, TelegramLoginReplay

User = get_user_model()


@pytest.mark.django_db
def test_user_normalizes_username_and_has_safe_defaults() -> None:
    user = User.objects.create_user(
        username="  Alice.Example ",
        password="Strong-password-123",
    )

    assert user.username == "alice.example"
    assert user.role == User.Role.USER
    assert user.is_active is True
    assert user.auth_version == 0
    assert user.check_password("Strong-password-123") is True


@pytest.mark.django_db
def test_username_is_case_insensitively_unique() -> None:
    User.objects.create_user(username="Alice", password="Strong-password-123")

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            User.objects.create_user(
                username=" alice ",
                password="Another-password-123",
            )


@pytest.mark.django_db
def test_username_model_validation_enforces_feature_bounds() -> None:
    for username in ("ab", "a" * 31, "bad space", "русский"):
        user = User(username=username)
        with pytest.raises(ValidationError):
            user.full_clean(validate_unique=False)


@pytest.mark.django_db
def test_refresh_session_and_replay_digest_are_unique() -> None:
    user = User.objects.create_user(username="alice", password=None)
    RefreshSession.objects.create(
        user=user,
        jti="refresh-jti",
        auth_version=user.auth_version,
        expires_at="2030-01-01T00:00:00Z",
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            RefreshSession.objects.create(
                user=user,
                jti="refresh-jti",
                auth_version=user.auth_version,
                expires_at="2030-01-01T00:00:00Z",
            )

    TelegramLoginReplay.objects.create(
        digest="a" * 64,
        expires_at="2030-01-01T00:00:00Z",
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            TelegramLoginReplay.objects.create(
                digest="a" * 64,
                expires_at="2030-01-01T00:00:00Z",
            )
