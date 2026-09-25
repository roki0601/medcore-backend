from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.common.exceptions import APIError

from .models import (
    USERNAME_VALIDATORS,
    RefreshSession,
    TelegramLoginReplay,
    User,
    UserProfile,
    canonicalize_username,
)


@dataclass(frozen=True)
class VerifiedTelegramPayload:
    telegram_id: int
    auth_date: datetime
    telegram_username: str | None
    data_check_string: str
    digest: str


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    access_expires_in: int


def _invalid_telegram(
    detail: str = "Telegram authentication payload is invalid.",
) -> APIError:
    return APIError(
        detail,
        code="AUTH_INVALID_TELEGRAM_PAYLOAD",
        status_code=401,
    )


def _canonical_fields(payload: dict[str, Any]) -> str:
    fields: dict[str, str] = {}
    for key, value in payload.items():
        if key == "hash" or value is None:
            continue
        if isinstance(value, (dict, list, tuple, bool)):
            raise _invalid_telegram()
        fields[key] = str(value)
    return "\n".join(f"{key}={fields[key]}" for key in sorted(fields))


def verify_telegram_payload(payload: dict[str, Any]) -> VerifiedTelegramPayload:
    """Verify the legacy Telegram Login Widget payload before database writes."""
    if not settings.TELEGRAM_BOT_TOKEN:
        raise _invalid_telegram()

    required = {"id", "auth_date", "hash"}
    if not required.issubset(payload):
        raise _invalid_telegram()

    telegram_id = payload["id"]
    auth_date_value = payload["auth_date"]
    provided_hash = payload["hash"]
    if (
        isinstance(telegram_id, bool)
        or not isinstance(telegram_id, int)
        or telegram_id <= 0
        or isinstance(auth_date_value, bool)
        or not isinstance(auth_date_value, int)
        or not isinstance(provided_hash, str)
        or len(provided_hash) != 64
    ):
        raise _invalid_telegram()

    data_check_string = _canonical_fields(payload)
    secret_key = hashlib.sha256(settings.TELEGRAM_BOT_TOKEN.encode()).digest()
    expected_hash = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected_hash, provided_hash.lower()):
        raise _invalid_telegram()
    try:
        auth_date = datetime.fromtimestamp(auth_date_value, tz=UTC)
    except (OverflowError, OSError, ValueError) as exc:
        raise _invalid_telegram() from exc
    age = (timezone.now() - auth_date).total_seconds()
    if (
        age > settings.TELEGRAM_AUTH_MAX_AGE
        or age < -settings.TELEGRAM_AUTH_FUTURE_SKEW
    ):
        raise _invalid_telegram()

    telegram_username = payload.get("username")
    if telegram_username is not None and not isinstance(telegram_username, str):
        raise _invalid_telegram()

    digest = hashlib.sha256(data_check_string.encode()).hexdigest()
    return VerifiedTelegramPayload(
        telegram_id=telegram_id,
        auth_date=auth_date,
        telegram_username=telegram_username,
        data_check_string=data_check_string,
        digest=digest,
    )


def _consume_replay(payload: VerifiedTelegramPayload) -> None:
    expires_at = payload.auth_date + timedelta(seconds=settings.TELEGRAM_AUTH_MAX_AGE)
    try:
        with transaction.atomic():
            TelegramLoginReplay.objects.create(
                digest=payload.digest,
                expires_at=expires_at,
            )
    except IntegrityError as exc:
        raise _invalid_telegram() from exc


def _is_valid_username(value: str) -> bool:
    try:
        for validator in USERNAME_VALIDATORS:
            validator(value)
    except ValidationError:
        return False
    return True


def _generate_username(telegram_id: int, telegram_username: str | None) -> str:
    if telegram_username:
        candidate = canonicalize_username(telegram_username)
        if (
            _is_valid_username(candidate)
            and not User.objects.filter(username=candidate).exists()
        ):
            return candidate

    base = f"user_{telegram_id}"
    candidate = base[:30]
    suffix = 1
    while User.objects.filter(username=candidate).exists():
        suffix_text = f"_{suffix}"
        candidate = f"{base[: 30 - len(suffix_text)]}{suffix_text}"
        suffix += 1
    return candidate


def _new_telegram_user(payload: VerifiedTelegramPayload) -> User:
    username = _generate_username(payload.telegram_id, payload.telegram_username)
    user = User(
        username=username,
        telegram_id=payload.telegram_id,
        telegram_username=payload.telegram_username,
        role=User.Role.USER,
        is_active=True,
    )
    user.set_unusable_password()
    user.full_clean(validate_unique=False, validate_constraints=False)
    user.save(force_insert=True)
    return user


def _require_jwt_key() -> None:
    if not settings.JWT_SIGNING_KEY:
        raise ImproperlyConfigured("JWT_SIGNING_KEY must be set.")


def _token_pair(user: User) -> TokenPair:
    _require_jwt_key()
    refresh = RefreshToken.for_user(user)
    refresh["auth_version"] = user.auth_version
    access = refresh.access_token
    access["auth_version"] = user.auth_version
    now_timestamp = int(timezone.now().timestamp())
    expires_in = max(0, int(access["exp"]) - now_timestamp)
    RefreshSession.objects.create(
        user=user,
        jti=str(refresh["jti"]),
        auth_version=user.auth_version,
        expires_at=datetime.fromtimestamp(
            int(refresh["exp"]),
            tz=UTC,
        ),
    )
    return TokenPair(
        access_token=str(access),
        refresh_token=str(refresh),
        access_expires_in=expires_in,
    )


def _is_unique_race(exc: IntegrityError) -> bool:
    diagnostic = getattr(getattr(exc, "__cause__", None), "diag", None)
    constraint_name = getattr(diagnostic, "constraint_name", None)
    return constraint_name in {
        "users_user_telegram_id_key",
        "users_user_username_key",
        "users_user_username_ci_unique",
    }


def _is_username_unique_race(exc: IntegrityError) -> bool:
    diagnostic = getattr(getattr(exc, "__cause__", None), "diag", None)
    constraint_name = getattr(diagnostic, "constraint_name", None)
    return constraint_name in {
        "users_user_username_key",
        "users_user_username_ci_unique",
    }


def authenticate_telegram(payload: dict[str, Any]) -> tuple[User, TokenPair]:
    verified = verify_telegram_payload(payload)
    for attempt in range(2):
        try:
            with transaction.atomic():
                _consume_replay(verified)
                user = (
                    User.objects.select_for_update()
                    .filter(telegram_id=verified.telegram_id)
                    .first()
                )
                if user is None:
                    user = _new_telegram_user(verified)
                elif not user.is_active:
                    raise APIError(
                        "User account is inactive.",
                        code="AUTH_USER_INACTIVE",
                        status_code=401,
                    )
                elif user.telegram_username != verified.telegram_username:
                    user.telegram_username = verified.telegram_username
                    user.save(update_fields=("telegram_username", "updated_at"))
                return user, _token_pair(user)
        except IntegrityError as exc:
            if attempt == 0 and _is_unique_race(exc):
                continue
            raise
    raise RuntimeError("Telegram authentication retry exhausted")


def authenticate_dev(persona: str) -> tuple[User, TokenPair]:
    if not (settings.DEBUG and getattr(settings, "DEV_AUTH_ENABLED", False)):
        raise APIError("Not found.", code="RESOURCE_NOT_FOUND", status_code=404)

    if persona not in ("demo", "premium"):
        raise APIError("Invalid persona.", code="INVALID_REQUEST", status_code=400)

    username = persona
    with transaction.atomic():
        user = User.objects.select_for_update().filter(username=username).first()
        if user is None:
            user = User(
                username=username,
                role=User.Role.USER,
                is_active=True,
            )
            user.set_unusable_password()
            user.full_clean(validate_unique=False, validate_constraints=False)
            user.save(force_insert=True)
        elif not user.is_active:
            raise APIError(
                "User account is inactive.",
                code="AUTH_USER_INACTIVE",
                status_code=401,
            )

        if persona == "premium":
            from apps.subscriptions.models import Plan, Subscription

            plan, _ = Plan.objects.get_or_create(
                code="premium-dev",
                defaults={
                    "title": "Dev Premium",
                    "price_rub": Decimal("0.00"),
                    "duration_days": 365,
                    "is_active": True,
                },
            )
            now = timezone.now()
            Subscription.objects.update_or_create(
                user=user,
                defaults={
                    "plan": plan,
                    "status": Subscription.Status.ACTIVE,
                    "starts_at": now,
                    "expires_at": now + timedelta(days=365),
                },
            )

        return user, _token_pair(user)


def refresh_access_token(raw_refresh_token: str) -> tuple[str, int]:
    _require_jwt_key()
    try:
        refresh = RefreshToken(raw_refresh_token)
    except TokenError as exc:
        raise APIError(
            "Refresh session is invalid or revoked.",
            code="AUTH_REFRESH_REVOKED",
            status_code=401,
        ) from exc

    jti = str(refresh["jti"])
    try:
        user_id = int(refresh["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise APIError(
            "Refresh session is invalid or revoked.",
            code="AUTH_REFRESH_REVOKED",
            status_code=401,
        ) from exc
    token_auth_version = refresh.get("auth_version")
    now = timezone.now()
    with transaction.atomic():
        try:
            session = (
                RefreshSession.objects.select_for_update()
                .select_related("user")
                .get(jti=jti)
            )
        except RefreshSession.DoesNotExist as exc:
            raise APIError(
                "Refresh session is invalid or revoked.",
                code="AUTH_REFRESH_REVOKED",
                status_code=401,
            ) from exc
        if session.user_id != user_id or session.revoked_at is not None:
            raise APIError(
                "Refresh session is invalid or revoked.",
                code="AUTH_REFRESH_REVOKED",
                status_code=401,
            )
        if session.expires_at <= now:
            raise APIError(
                "Refresh session is invalid or revoked.",
                code="AUTH_REFRESH_REVOKED",
                status_code=401,
            )
        if not session.user.is_active:
            raise APIError(
                "User account is inactive.",
                code="AUTH_USER_INACTIVE",
                status_code=401,
            )
        try:
            auth_version_matches = (
                token_auth_version is not None
                and int(token_auth_version) == session.auth_version
                and session.user.auth_version == session.auth_version
            )
        except (TypeError, ValueError):
            auth_version_matches = False
        if not auth_version_matches:
            raise APIError(
                "Refresh session is invalid or revoked.",
                code="AUTH_REFRESH_REVOKED",
                status_code=401,
            )

        access = refresh.access_token
        access["auth_version"] = session.user.auth_version
        session.last_used_at = now
        session.save(update_fields=("last_used_at",))
        expires_in = max(0, int(access["exp"]) - int(now.timestamp()))
        return str(access), expires_in


def revoke_refresh_session(raw_refresh_token: str | None) -> None:
    if not raw_refresh_token:
        return
    try:
        refresh = RefreshToken(raw_refresh_token)
    except TokenError:
        return
    RefreshSession.objects.filter(
        jti=str(refresh["jti"]),
        revoked_at__isnull=True,
    ).update(revoked_at=timezone.now())


def revoke_all_sessions(user: User) -> None:
    with transaction.atomic():
        RefreshSession.objects.filter(
            user=user,
            revoked_at__isnull=True,
        ).update(revoked_at=timezone.now())


def normalize_username(value: str) -> str:
    if not isinstance(value, str):
        raise APIError(
            "Username is invalid.",
            code="VALIDATION_ERROR",
            status_code=422,
            fields={"username": ["Username must be a string."]},
        )
    normalized = canonicalize_username(value)
    try:
        for validator in USERNAME_VALIDATORS:
            validator(normalized)
    except ValidationError as exc:
        raise APIError(
            "Username is invalid.",
            code="VALIDATION_ERROR",
            status_code=422,
            fields={"username": [str(exc)]},
        ) from exc
    return normalized


def update_username(user: User, username: str) -> User:
    normalized = normalize_username(username)
    try:
        with transaction.atomic():
            locked_user = User.objects.select_for_update().get(pk=user.pk)
            locked_user.username = normalized
            locked_user.save(update_fields=("username", "updated_at"))
            return locked_user
    except IntegrityError as exc:
        if not _is_username_unique_race(exc):
            raise
        raise APIError(
            "Username is already taken.",
            code="USERNAME_TAKEN",
            status_code=409,
        ) from exc


def delete_account(user: User) -> None:
    with transaction.atomic():
        locked_user = User.objects.select_for_update().get(pk=user.pk)
        now = timezone.now()
        RefreshSession.objects.filter(
            user=locked_user,
            revoked_at__isnull=True,
        ).update(revoked_at=now)
        locked_user.delete()


def get_or_create_profile(user: User) -> UserProfile:
    profile, _ = UserProfile.objects.prefetch_related(
        "selected_subjects"
    ).get_or_create(user=user)
    return profile


def update_profile(
    user: User,
    *,
    university: str | None = ...,
    course: int | None = ...,
    semester_goal: str | None = ...,
    daily_study_minutes: int | None = ...,
    subject_ids: list[int] | None = None,
) -> UserProfile:
    with transaction.atomic():
        profile, _ = UserProfile.objects.select_for_update().get_or_create(user=user)
        update_fields = []
        if university is not ...:
            profile.university = (university or "").strip()
            update_fields.append("university")
        if course is not ...:
            profile.course = course
            update_fields.append("course")
        if semester_goal is not ...:
            profile.semester_goal = (semester_goal or "").strip()
            update_fields.append("semester_goal")
        if daily_study_minutes is not ...:
            profile.daily_study_minutes = daily_study_minutes
            update_fields.append("daily_study_minutes")

        if update_fields:
            update_fields.append("updated_at")
            profile.save(update_fields=update_fields)

        if subject_ids is not None:
            profile.selected_subjects.set(subject_ids)

        return UserProfile.objects.prefetch_related("selected_subjects").get(
            pk=profile.pk
        )
