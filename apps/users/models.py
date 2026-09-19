from __future__ import annotations

import unicodedata

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import UserManager as DjangoUserManager
from django.core.validators import (
    MaxLengthValidator,
    MinLengthValidator,
    RegexValidator,
)
from django.db import models
from django.db.models.functions import Lower

USERNAME_PATTERN = r"^[a-z0-9._-]+$"
USERNAME_VALIDATORS = (
    MinLengthValidator(3),
    MaxLengthValidator(30),
    RegexValidator(
        regex=USERNAME_PATTERN,
        message=(
            "Username may contain only lowercase Latin letters, digits, "
            "dot, underscore and hyphen."
        ),
    ),
)


def canonicalize_username(value: str) -> str:
    """Return the canonical application username representation."""
    return unicodedata.normalize("NFKC", value).strip().lower()


class UserManager(DjangoUserManager):
    def _create_user(self, username, email, password, **extra_fields):
        if not username:
            raise ValueError("The username must be set")
        user = self.model(
            username=canonicalize_username(username),
            email=email,
            **extra_fields,
        )
        if password is None:
            user.set_unusable_password()
        else:
            user.set_password(password)
        user.full_clean(validate_unique=False, validate_constraints=False)
        user.save(using=self._db)
        return user


class User(AbstractUser):
    class Role(models.TextChoices):
        USER = "user", "User"
        EDITOR = "editor", "Editor"
        ADMIN = "admin", "Admin"

    username = models.CharField(
        max_length=30,
        unique=True,
        validators=USERNAME_VALIDATORS,
    )
    email = models.EmailField(max_length=254, null=True, blank=True)
    telegram_id = models.BigIntegerField(null=True, blank=True, unique=True)
    telegram_username = models.CharField(max_length=255, null=True, blank=True)
    role = models.CharField(
        max_length=20,
        choices=Role,
        default=Role.USER,
    )
    auth_version = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower("username"),
                name="users_user_username_ci_unique",
            ),
            models.CheckConstraint(
                condition=~models.Q(username=""),
                name="users_user_username_not_blank",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        self.username = canonicalize_username(self.username or "")

    def save(self, *args, **kwargs):
        self.username = canonicalize_username(self.username or "")
        return super().save(*args, **kwargs)


class RefreshSession(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="refresh_sessions",
    )
    jti = models.CharField(max_length=64, unique=True)
    auth_version = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(
                fields=("user", "revoked_at"),
                name="users_refresh_user_revoked_idx",
            ),
            models.Index(
                fields=("expires_at",),
                name="users_refresh_expires_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"Refresh session {self.pk}"


class TelegramLoginReplay(models.Model):
    digest = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(
                fields=("expires_at",),
                name="users_replay_expires_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"Telegram replay {self.pk}"
