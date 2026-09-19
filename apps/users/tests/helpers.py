from __future__ import annotations

import hashlib
import hmac
import time

TEST_BOT_TOKEN = "123456:unit-test-bot-token"


def telegram_payload(
    *,
    telegram_id: int = 123456789,
    auth_date: int | None = None,
    username: str | None = "anna_example",
    first_name: str = "Anna",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": telegram_id,
        "first_name": first_name,
        "auth_date": auth_date or int(time.time()),
    }
    if username is not None:
        payload["username"] = username
    data_check_string = "\n".join(f"{key}={payload[key]}" for key in sorted(payload))
    secret_key = hashlib.sha256(TEST_BOT_TOKEN.encode()).digest()
    payload["hash"] = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256,
    ).hexdigest()
    return payload


def csrf_headers(client) -> dict[str, str]:
    response = client.get("/api/v1/auth/csrf/")
    assert response.status_code == 200
    return {"HTTP_X_CSRFTOKEN": response.json()["csrf_token"]}
