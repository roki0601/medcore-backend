from __future__ import annotations

import hashlib
import hmac
import urllib.parse
from decimal import Decimal
from typing import TYPE_CHECKING

from django.conf import settings

if TYPE_CHECKING:
    from .models import Payment


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
    """
    raw = f"{merchant_login}:{out_sum}:{inv_id}:{password_1}"
    algo = hash_algorithm.lower()
    if algo == "sha256":
        return hashlib.sha256(raw.encode("utf-8")).hexdigest().lower()
    elif algo == "md5":
        return hashlib.md5(raw.encode("utf-8")).hexdigest().lower()
    else:
        raise ValueError(f"Unsupported Robokassa hash algorithm: {hash_algorithm}")


def calculate_result_signature(
    out_sum: str,
    inv_id: int | str,
    password_2: str,
    hash_algorithm: str = "sha256",
) -> str:
    """Calculate Robokassa ResultURL callback signature using Password #2.

    Raw string: OutSum:InvId:Password_2
    """
    raw = f"{out_sum}:{inv_id}:{password_2}"
    algo = hash_algorithm.lower()
    if algo == "sha256":
        return hashlib.sha256(raw.encode("utf-8")).hexdigest().lower()
    elif algo == "md5":
        return hashlib.md5(raw.encode("utf-8")).hexdigest().lower()
    else:
        raise ValueError(f"Unsupported Robokassa hash algorithm: {hash_algorithm}")


def verify_result_signature(
    out_sum: str,
    inv_id: int | str,
    received_signature: str,
    password_2: str | None = None,
    hash_algorithm: str | None = None,
) -> bool:
    """Verify Robokassa ResultURL signature using constant-time comparison."""

    pwd_2 = (
        password_2
        if password_2 is not None
        else getattr(settings, "ROBOKASSA_PASSWORD_2", "")
    )
    algo = (
        hash_algorithm
        if hash_algorithm is not None
        else getattr(settings, "ROBOKASSA_HASH_ALGORITHM", "sha256")
    )
    expected = calculate_result_signature(
        out_sum=out_sum,
        inv_id=inv_id,
        password_2=pwd_2,
        hash_algorithm=algo,
    )
    return hmac.compare_digest(expected, received_signature.strip().lower())


def build_payment_url(payment: Payment) -> str:
    """Build payment checkout URL for redirecting buyer to Robokassa."""
    merchant_login = getattr(settings, "ROBOKASSA_MERCHANT_LOGIN", "")
    password_1 = getattr(settings, "ROBOKASSA_PASSWORD_1", "")
    hash_algorithm = getattr(settings, "ROBOKASSA_HASH_ALGORITHM", "sha256")
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

    user_email = getattr(payment.user, "email", "")
    if user_email:
        params["Email"] = user_email

    return f"{base_url}?{urllib.parse.urlencode(params)}"
