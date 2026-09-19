from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

from apps.common.exceptions import APIError
from apps.users.models import RefreshSession, TelegramLoginReplay, User
from apps.users.services import (
    authenticate_telegram,
    refresh_access_token,
    revoke_refresh_session,
    update_username,
    verify_telegram_payload,
)

from .helpers import TEST_BOT_TOKEN, telegram_payload


@pytest.fixture(autouse=True)
def configure_telegram(settings):
    settings.TELEGRAM_BOT_TOKEN = TEST_BOT_TOKEN
    settings.TELEGRAM_AUTH_MAX_AGE = 86400
    settings.TELEGRAM_AUTH_FUTURE_SKEW = 60


@pytest.mark.django_db
def test_valid_payload_verifies_with_canonical_digest() -> None:
    payload = telegram_payload()

    verified = verify_telegram_payload(payload)

    assert verified.telegram_id == payload["id"]
    assert len(verified.digest) == 64
    assert "hash=" not in verified.data_check_string


@pytest.mark.django_db
def test_invalid_signature_and_stale_payload_are_rejected() -> None:
    invalid = telegram_payload()
    invalid["hash"] = "0" * 64
    with pytest.raises(APIError) as invalid_error:
        verify_telegram_payload(invalid)
    assert invalid_error.value.default_code == "AUTH_INVALID_TELEGRAM_PAYLOAD"

    stale = telegram_payload(auth_date=int(time.time()) - 86401)
    with pytest.raises(APIError) as stale_error:
        verify_telegram_payload(stale)
    assert stale_error.value.default_code == "AUTH_INVALID_TELEGRAM_PAYLOAD"

    missing = telegram_payload()
    del missing["id"]
    with pytest.raises(APIError) as missing_error:
        verify_telegram_payload(missing)
    assert missing_error.value.default_code == "AUTH_INVALID_TELEGRAM_PAYLOAD"

    future = telegram_payload(auth_date=int(time.time()) + 61)
    with pytest.raises(APIError) as future_error:
        verify_telegram_payload(future)
    assert future_error.value.default_code == "AUTH_INVALID_TELEGRAM_PAYLOAD"


@pytest.mark.django_db
def test_exact_payload_replay_is_rejected_before_second_session() -> None:
    payload = telegram_payload()

    user, first_tokens = authenticate_telegram(payload)

    with pytest.raises(APIError) as replay_error:
        authenticate_telegram(payload)

    assert replay_error.value.default_code == "AUTH_INVALID_TELEGRAM_PAYLOAD"
    assert RefreshSession.objects.filter(user=user).count() == 1
    assert TelegramLoginReplay.objects.count() == 1
    assert first_tokens.refresh_token


@pytest.mark.django_db
def test_fresh_payload_finds_existing_user_without_mutating_app_username() -> None:
    first = telegram_payload(telegram_id=987654321, username="first_name")
    user, _ = authenticate_telegram(first)
    fresh = telegram_payload(
        telegram_id=987654321,
        auth_date=int(time.time()) + 1,
        username="changed_telegram_name",
    )

    same_user, _ = authenticate_telegram(fresh)

    user.refresh_from_db()
    assert same_user.pk == user.pk
    assert user.username == "first_name"
    assert user.telegram_username == "changed_telegram_name"
    assert RefreshSession.objects.filter(user=user).count() == 2


@pytest.mark.django_db(transaction=True)
def test_concurrent_first_logins_share_one_user():
    auth_date = int(time.time())
    payloads = [
        telegram_payload(
            telegram_id=989898989,
            auth_date=auth_date,
            username="race_one",
        ),
        telegram_payload(
            telegram_id=989898989,
            auth_date=auth_date,
            username="race_two",
        ),
    ]

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(authenticate_telegram, payloads))

    user_ids = {user.pk for user, _ in results}
    assert len(user_ids) == 1
    user_id = user_ids.pop()
    assert User.objects.filter(pk=user_id, telegram_id=989898989).count() == 1
    assert RefreshSession.objects.filter(user_id=user_id).count() == 2


@pytest.mark.django_db
def test_missing_telegram_username_gets_unique_fallback() -> None:
    user, _ = authenticate_telegram(
        telegram_payload(telegram_id=777777777, username=None)
    )

    assert user.username == "user_777777777"


@pytest.mark.django_db
def test_refresh_checks_revocation_and_updates_last_used_at() -> None:
    user, tokens = authenticate_telegram(telegram_payload(telegram_id=333333333))

    access_token, expires_in = refresh_access_token(tokens.refresh_token)

    assert access_token
    assert expires_in > 0
    session = RefreshSession.objects.get(user=user)
    assert session.last_used_at is not None

    revoke_refresh_session(tokens.refresh_token)
    with pytest.raises(APIError) as error:
        refresh_access_token(tokens.refresh_token)
    assert error.value.default_code == "AUTH_REFRESH_REVOKED"


@pytest.mark.django_db
def test_refresh_fails_closed_without_dedicated_jwt_key(settings):
    _, tokens = authenticate_telegram(telegram_payload(telegram_id=353535353))
    settings.JWT_SIGNING_KEY = ""

    with pytest.raises(ImproperlyConfigured):
        refresh_access_token(tokens.refresh_token)


@pytest.mark.django_db(transaction=True)
def test_refresh_and_revoke_race_leaves_session_revoked():
    _, tokens = authenticate_telegram(telegram_payload(telegram_id=343434343))

    def attempt_refresh():
        try:
            refresh_access_token(tokens.refresh_token)
        except APIError as exc:
            return exc.default_code
        return "REFRESHED"

    def revoke():
        revoke_refresh_session(tokens.refresh_token)
        return "REVOKED"

    with ThreadPoolExecutor(max_workers=2) as executor:
        refresh_result, revoke_result = executor.map(
            lambda operation: operation(),
            (attempt_refresh, revoke),
        )

    assert refresh_result in {"REFRESHED", "AUTH_REFRESH_REVOKED"}
    assert revoke_result == "REVOKED"
    with pytest.raises(APIError) as final_error:
        refresh_access_token(tokens.refresh_token)
    assert final_error.value.default_code == "AUTH_REFRESH_REVOKED"


@pytest.mark.django_db
def test_username_update_normalizes_and_rejects_collision() -> None:
    first, _ = authenticate_telegram(telegram_payload(telegram_id=444444444))
    second, _ = authenticate_telegram(
        telegram_payload(telegram_id=555555555, auth_date=int(time.time()) + 1)
    )

    updated = update_username(first, "  New.Name ")

    assert updated.username == "new.name"
    with pytest.raises(APIError) as error:
        update_username(second, "NEW.NAME")
    assert error.value.default_code == "USERNAME_TAKEN"


@pytest.mark.django_db(transaction=True)
def test_concurrent_username_updates_return_one_conflict():
    first, _ = authenticate_telegram(telegram_payload(telegram_id=454545454))
    second, _ = authenticate_telegram(
        telegram_payload(telegram_id=464646464, auth_date=int(time.time()) + 1)
    )

    def update(user):
        try:
            update_username(user, "same_race_name")
        except APIError as exc:
            return exc.default_code
        return "UPDATED"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(update, (first, second)))

    assert sorted(results) == ["UPDATED", "USERNAME_TAKEN"]


@pytest.mark.django_db
def test_delete_revokes_sessions_before_user_delete():
    user, tokens = authenticate_telegram(telegram_payload(telegram_id=666666666))
    session = RefreshSession.objects.get(user=user)
    now_before = timezone.now()

    from apps.users.services import delete_account

    delete_account(user)

    assert not RefreshSession.objects.filter(pk=session.pk).exists()
    assert timezone.now() >= now_before
    with pytest.raises(APIError):
        refresh_access_token(tokens.refresh_token)


@pytest.mark.django_db
def test_auth_paths_never_log_payload_or_token_secrets(caplog) -> None:
    payload = telegram_payload(telegram_id=999888777)

    with caplog.at_level(logging.DEBUG):
        _, tokens = authenticate_telegram(payload)
        refresh_access_token(tokens.refresh_token)
        with pytest.raises(APIError):
            refresh_access_token("not-a-valid-refresh-token")

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert TEST_BOT_TOKEN not in logged
    assert payload["hash"] not in logged
    assert tokens.access_token not in logged
    assert tokens.refresh_token not in logged
