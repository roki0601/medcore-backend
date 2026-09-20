from __future__ import annotations

import hashlib
import hmac
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


def format_out_sum(amount: Decimal | float | str) -> str:
    """Format payment amount to 2 decimal places as required by Robokassa."""
    dec = Decimal(str(amount)) if not isinstance(amount, Decimal) else amount
    return f"{dec:.2f}"


def calculate_payment_signature(
    merchant_login: str,
    out_sum: str,
    inv_id: int | str,
    password_1: str,
    hash_algorithm: str = "sha256",
) -> str:
    """Calculate Robokassa payment initialization signature using Password #1.

    Raw string: MerchantLogin:OutSum:InvId:Password_1
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
    pwd_2 = (
        password_2
        if password_2 is not None
        else getattr(settings, "ROBOKASSA_PASSWORD_2", "")
    )
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
    merchant_login = getattr(settings, "ROBOKASSA_MERCHANT_LOGIN", "")
    password_1 = getattr(settings, "ROBOKASSA_PASSWORD_1", "")
    hash_algorithm = getattr(settings, "ROBOKASSA_HASH_ALGORITHM", "sha256")

    if not str(merchant_login).strip() or not str(password_1).strip():
        raise RobokassaConfigurationError(
            "Robokassa merchant login or Password #1 is not configured."
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

    merchant_login = getattr(settings, "ROBOKASSA_MERCHANT_LOGIN", "").strip()
    password_1 = getattr(settings, "ROBOKASSA_PASSWORD_1", "").strip()
    hash_algorithm = (
        getattr(settings, "ROBOKASSA_HASH_ALGORITHM", "sha256").strip().lower()
    )
    test_mode = getattr(settings, "ROBOKASSA_TEST_MODE", True)
    base_url = getattr(
        settings,
        "ROBOKASSA_BASE_URL",
        "https://auth.robokassa.ru/Merchant/Index.aspx",
    )

    out_sum = format_out_sum(payment.amount)
    signature = calculate_payment_signature(
        merchant_login=merchant_login,
        out_sum=out_sum,
        inv_id=payment.pk,
        password_1=password_1,
        hash_algorithm=hash_algorithm,
    )

    params: dict[str, str] = {
        "MerchantLogin": merchant_login,
        "OutSum": out_sum,
        "InvId": str(payment.pk),
        "Description": f"Подписка: {payment.plan.title}",
        "SignatureValue": signature,
    }

    if test_mode:
        params["IsTest"] = "1"

    user_email = getattr(payment.user, "email", "") if payment.user else ""
    if user_email:
        params["Email"] = user_email

    return f"{base_url}?{urllib.parse.urlencode(params)}"
