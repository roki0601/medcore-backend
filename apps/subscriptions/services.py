from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Payment, Plan, Subscription
from .robokassa import build_payment_url, verify_result_signature

logger = logging.getLogger(__name__)


def create_payment(*, user, plan_id: int) -> tuple[Payment, str]:
    """Create a pending Payment record snapshotting Plan price and return checkout URL.

    Raises:
        ValidationError: if the plan does not exist or is inactive.
    """
    plan = Plan.objects.filter(id=plan_id, is_active=True).first()
    if plan is None:
        raise ValidationError({"plan_id": "Активный план подписки не найден."})

    with transaction.atomic():
        payment = Payment.objects.create(
            user=user,
            plan=plan,
            amount=plan.price_rub,
            status=Payment.Status.PENDING,
            provider="robokassa",
        )
        payment_url = build_payment_url(payment)

    return payment, payment_url


def process_robokassa_result(
    *,
    inv_id: int,
    out_sum: str,
    signature: str,
) -> tuple[bool, str]:
    """Validate Robokassa ResultURL notification and activate subscription.

    Returns:
        tuple (success, message):
            success: bool indicating whether notification was accepted.
            message: text body to return to Robokassa (e.g., 'OK{inv_id}' on success).
    """
    if not verify_result_signature(
        out_sum=out_sum,
        inv_id=inv_id,
        received_signature=signature,
    ):
        logger.warning(
            "Robokassa ResultURL signature verification failed for InvId=%s",
            inv_id,
        )
        return False, "bad signature"

    try:
        dec_out_sum = Decimal(out_sum)
    except (InvalidOperation, TypeError, ValueError):
        logger.warning(
            "Robokassa ResultURL invalid amount format for InvId=%s: %s",
            inv_id,
            out_sum,
        )
        return False, "invalid amount format"

    with transaction.atomic():
        payment = (
            Payment.objects.select_for_update()
            .filter(id=inv_id)
            .select_related("plan", "user")
            .first()
        )
        if payment is None:
            logger.warning("Robokassa ResultURL payment not found for InvId=%s", inv_id)
            return False, "payment not found"

        if payment.amount != dec_out_sum:
            logger.warning(
                "Robokassa ResultURL amount mismatch for InvId=%s: expected %s, got %s",
                inv_id,
                payment.amount,
                dec_out_sum,
            )
            return False, "amount mismatch"

        if payment.status == Payment.Status.SUCCEEDED:
            # Idempotent response: callback was already processed.
            logger.info("Robokassa ResultURL duplicate callback for InvId=%s", inv_id)
            return True, f"OK{inv_id}"

        now = timezone.now()
        payment.status = Payment.Status.SUCCEEDED
        payment.paid_at = now

        subscription = Subscription.objects.create(
            user=payment.user,
            plan=payment.plan,
            status=Subscription.Status.ACTIVE,
            starts_at=now,
            expires_at=now + timedelta(days=payment.plan.duration_days),
        )

        payment.subscription = subscription
        payment.save(update_fields=["status", "paid_at", "subscription", "updated_at"])

        logger.info(
            "Robokassa payment #%s succeeded, subscription #%s activated for user #%s",
            payment.id,
            subscription.id,
            payment.user_id,
        )

    return True, f"OK{inv_id}"
