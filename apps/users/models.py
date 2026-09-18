import unicodedata

from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import UserManager as DjangoUserManager
from django.db import models
from django.db.models.functions import Lower


def canonicalize_username(value: str) -> str:
    """Return the canonical identifier used by the password auth flow."""
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
        user.set_password(password)
        user.save(using=self._db)
        return user


class User(AbstractUser):
    class Role(models.TextChoices):
        USER = "user", "User"
        EDITOR = "editor", "Editor"
        ADMIN = "admin", "Admin"

    username = models.CharField(max_length=150, unique=True)
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
        self.username = canonicalize_username(self.username)

    def save(self, *args, **kwargs):
        self.username = canonicalize_username(self.username)
        return super().save(*args, **kwargs)
