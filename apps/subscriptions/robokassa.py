from __future__ import annotations

import hashlib
import hmac
import json
import logging
import urllib.parse
from decimal import Decimal
from typing import TYPE_CHECKING

from django.conf import settings

if TYPE_CHECKING:
    from .models import Payment

logger = logging.getLogger(__name__)

SUPPORTED_ROBOKASSA_HASH_ALGORITHMS = {"md5", "sha256"}


class RobokassaConfigurationError(ValueError):
    """Raised when Robokassa provider is invoked without valid configuration."""


class RobokassaReceiptEncoder(json.JSONEncoder):
    """JSON encoder preserving Decimal precision without float conversion."""

    def iterencode(self, o, _one_shot=False):
        def _encode(obj):
            if isinstance(obj, Decimal):
                yield f"{obj:.2f}"
            elif isinstance(obj, dict):
                yield "{"
                first = True
                for key, val in obj.items():
                    if not first:
                        yield ","
                    first = False
                    yield json.dumps(str(key), ensure_ascii=False)
                    yield ":"
                    yield from _encode(val)
                yield "}"
            elif isinstance(obj, (list, tuple)):
                yield "["
                first = True
                for item in obj:
                    if not first:
                        yield ","
                    first = False
                    yield from _encode(item)
                yield "]"
            else:
                yield json.dumps(obj, ensure_ascii=False)

        return _encode(o)


def build_receipt(payment: Payment) -> dict:
    """Build fiscal receipt structure according to Robokassa FZ-54 specification.

    Configured for self-employed status (Робочеки СМЗ + Мой налог):
    - Single item corresponding to the purchased plan.
    - quantity: 1
    - sum: strictly equal to payment.amount (Decimal)
    - payment_method: "full_payment" (полный расчет)
    - payment_object: "service" (услуга)
    - tax: "none" (без НДС)
    - name: consumer-facing title without internal IDs or technical slugs.
    """
    duration = payment.plan.duration_days
    item_name = f"Доступ к образовательной платформе Medcore — {duration} дней"
    return {
        "items": [
            {
                "name": item_name,
                "quantity": 1,
                "sum": payment.amount,
                "payment_method": "full_payment",
                "payment_object": "service",
                "tax": "none",
            }
        ]
    }


def serialize_receipt(payment_or_dict: Payment | dict) -> str:
    """Serialize receipt payload to compact, deterministic UTF-8 JSON.

    Monetary values are formatted strictly with 2 decimal places from Decimal,
    avoiding float conversion or rounding loss.
    """
    if isinstance(payment_or_dict, dict):
        receipt_dict = payment_or_dict
    else:
        receipt_dict = build_receipt(payment_or_dict)

    return json.dumps(receipt_dict, cls=RobokassaReceiptEncoder, ensure_ascii=False)


def _setting_text(name: str) -> str:
    return str(getattr(settings, name, "")).strip()


def robokassa_test_mode() -> bool:
    return bool(getattr(settings, "ROBOKASSA_TEST_MODE", False))


def active_robokassa_password_1() -> str:
    """Password #1 for the active cabinet: test pair when test mode is on."""
    if robokassa_test_mode():
        return _setting_text("ROBOKASSA_TEST_PASSWORD_1")
    return _setting_text("ROBOKASSA_PASSWORD_1")


def active_robokassa_password_2() -> str:
    """Password #2 for the active cabinet: test pair when test mode is on."""
    if robokassa_test_mode():
        return _setting_text("ROBOKASSA_TEST_PASSWORD_2")
    return _setting_text("ROBOKASSA_PASSWORD_2")


def format_out_sum(amount: Decimal | float | str) -> str:
    """Format payment amount to 2 decimal places as required by Robokassa."""
    dec = Decimal(str(amount)) if not isinstance(amount, Decimal) else amount
    return f"{dec:.2f}"


def calculate_payment_signature(
    merchant_login: str,
    out_sum: str,
    inv_id: int | str,
    password_1: str,
    receipt: str | None = None,
    hash_algorithm: str = "sha256",
) -> str:
    """Calculate Robokassa payment initialization signature using Password #1.

    Raw string without receipt: MerchantLogin:OutSum:InvId:Password_1
    Raw string with receipt:    MerchantLogin:OutSum:InvId:Receipt:Password_1

    According to Robokassa documentation, the Receipt parameter in the signature
    string MUST be URL-encoded (RFC 3986 percent-encoded). If a raw JSON string
    is passed, it is URL-encoded automatically.

    Fails closed if credentials are missing or algorithm is unsupported.
    """
    if not str(merchant_login).strip():
        raise RobokassaConfigurationError("Merchant login must not be empty.")
    if not str(password_1).strip():
        raise RobokassaConfigurationError("Password #1 must not be empty.")

    algo = str(hash_algorithm).strip().lower()
    if algo not in SUPPORTED_ROBOKASSA_HASH_ALGORITHMS:
        raise RobokassaConfigurationError(
            f"Unsupported Robokassa hash algorithm: {hash_algorithm}"
        )

    if receipt is not None:
        receipt_str = str(receipt).strip()
        if receipt_str:
            if receipt_str.startswith("{") or receipt_str.startswith("["):
                encoded_receipt = urllib.parse.quote(receipt_str, safe="")
            else:
                encoded_receipt = receipt_str
            raw = f"{merchant_login}:{out_sum}:{inv_id}:{encoded_receipt}:{password_1}"
        else:
            raw = f"{merchant_login}:{out_sum}:{inv_id}:{password_1}"
    else:
        raw = f"{merchant_login}:{out_sum}:{inv_id}:{password_1}"

    if algo == "sha256":
        return hashlib.sha256(raw.encode()).hexdigest().lower()
    return hashlib.md5(raw.encode()).hexdigest().lower()


def calculate_result_signature(
    out_sum: str,
    inv_id: int | str,
    password_2: str,
    hash_algorithm: str = "sha256",
) -> str:
    """Calculate Robokassa ResultURL callback signature using Password #2.

    Raw string: OutSum:InvId:Password_2
    Fails closed if Password #2 is missing or algorithm is unsupported.
    """
    if not str(password_2).strip():
        raise RobokassaConfigurationError("Password #2 must not be empty.")

    algo = str(hash_algorithm).strip().lower()
    if algo not in SUPPORTED_ROBOKASSA_HASH_ALGORITHMS:
        raise RobokassaConfigurationError(
            f"Unsupported Robokassa hash algorithm: {hash_algorithm}"
        )

    raw = f"{out_sum}:{inv_id}:{password_2}"
    if algo == "sha256":
        return hashlib.sha256(raw.encode()).hexdigest().lower()
    return hashlib.md5(raw.encode()).hexdigest().lower()


def verify_result_signature(
    out_sum: str,
    inv_id: int | str,
    received_signature: str,
    password_2: str | None = None,
    hash_algorithm: str | None = None,
) -> bool:
    """Verify Robokassa ResultURL signature using constant-time comparison.

    Fails closed if Password #2 is empty or hash_algorithm is unsupported.
    """
    pwd_2 = password_2 if password_2 is not None else active_robokassa_password_2()
    pwd_2_str = str(pwd_2).strip()
    if not pwd_2_str:
        logger.error(
            "Robokassa ResultURL verification failed closed: "
            "Password #2 is not configured."
        )
        return False

    algo = (
        hash_algorithm
        if hash_algorithm is not None
        else getattr(settings, "ROBOKASSA_HASH_ALGORITHM", "sha256")
    )
    algo_str = str(algo).strip().lower()
    if algo_str not in SUPPORTED_ROBOKASSA_HASH_ALGORITHMS:
        logger.error(
            "Robokassa ResultURL verification failed closed: "
            "unsupported hash algorithm."
        )
        return False

    try:
        expected = calculate_result_signature(
            out_sum=out_sum,
            inv_id=inv_id,
            password_2=pwd_2_str,
            hash_algorithm=algo_str,
        )
    except RobokassaConfigurationError:
        return False

    return hmac.compare_digest(expected, received_signature.strip().lower())


def validate_robokassa_configuration() -> None:
    """Ensure Robokassa payment settings are present and valid."""
    merchant_login = _setting_text("ROBOKASSA_MERCHANT_LOGIN")
    password_1 = active_robokassa_password_1()
    password_2 = active_robokassa_password_2()
    hash_algorithm = getattr(settings, "ROBOKASSA_HASH_ALGORITHM", "sha256")

    if not merchant_login or not password_1 or not password_2:
        mode = "test" if robokassa_test_mode() else "live"
        raise RobokassaConfigurationError(
            f"Robokassa merchant login or {mode} passwords are not configured."
        )

    algo = str(hash_algorithm).strip().lower()
    if algo not in SUPPORTED_ROBOKASSA_HASH_ALGORITHMS:
        raise RobokassaConfigurationError(
            f"Unsupported Robokassa hash algorithm: {hash_algorithm}"
        )


def build_payment_url(payment: Payment) -> str:
    """Build payment checkout URL for redirecting buyer to Robokassa.

    Raises:
        RobokassaConfigurationError: if secrets or algorithm are unconfigured.
    """
    validate_robokassa_configuration()

    merchant_login = _setting_text("ROBOKASSA_MERCHANT_LOGIN")
    password_1 = active_robokassa_password_1()
    hash_algorithm = (
        getattr(settings, "ROBOKASSA_HASH_ALGORITHM", "sha256").strip().lower()
    )
    test_mode = robokassa_test_mode()
    base_url = getattr(
        settings,
        "ROBOKASSA_BASE_URL",
        "https://auth.robokassa.ru/Merchant/Index.aspx",
    )

    out_sum = format_out_sum(payment.amount)
    receipt_json = serialize_receipt(payment)
    receipt_encoded = urllib.parse.quote(receipt_json, safe="")

    signature = calculate_payment_signature(
        merchant_login=merchant_login,
        out_sum=out_sum,
        inv_id=payment.pk,
        password_1=password_1,
        receipt=receipt_encoded,
        hash_algorithm=hash_algorithm,
    )

    params: dict[str, str] = {
        "MerchantLogin": merchant_login,
        "OutSum": out_sum,
        "InvId": str(payment.pk),
        "Description": f"Подписка: {payment.plan.title}",
        "Receipt": receipt_encoded,
        "SignatureValue": signature,
    }

    if test_mode:
        params["IsTest"] = "1"

    user_email = getattr(payment.user, "email", "") if payment.user else ""
    if user_email:
        params["Email"] = user_email

    query_string = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    return f"{base_url}?{query_string}"
