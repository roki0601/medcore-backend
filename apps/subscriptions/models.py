from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

SUBSCRIPTION_STATUS_VALUES = ("active", "cancelled")
PAYMENT_STATUS_VALUES = ("pending", "succeeded", "failed")


class Plan(models.Model):
    code = models.SlugField(max_length=50, unique=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    price_rub = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    duration_days = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("price_rub", "duration_days", "id")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(duration_days__gt=0),
                name="subscriptions_plan_duration_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(price_rub__gte=Decimal("0.00")),
                name="subscriptions_plan_price_non_negative",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.code})"


class Subscription(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        CANCELLED = "cancelled", "Cancelled"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )
    plan = models.ForeignKey(
        Plan,
        on_delete=models.PROTECT,
        related_name="subscriptions",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )
    starts_at = models.DateTimeField(db_index=True)
    expires_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-expires_at", "-id")
        indexes = [
            models.Index(
                fields=("user", "status", "expires_at"),
                name="sub_user_status_exp_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=SUBSCRIPTION_STATUS_VALUES),
                name="subscriptions_sub_status_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(expires_at__gt=models.F("starts_at")),
                name="subscriptions_sub_dates_valid",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.starts_at and self.expires_at and self.expires_at <= self.starts_at:
            raise ValidationError(
                {
                    "expires_at": (
                        "Expiration timestamp must be strictly after start timestamp."
                    )
                }
            )

    def is_current_for(self, timestamp) -> bool:
        """Check if subscription grants entitlement at the given UTC timestamp."""
        return (
            self.status in (self.Status.ACTIVE, self.Status.CANCELLED)
            and self.starts_at <= timestamp < self.expires_at
        )

    def __str__(self) -> str:
        return f"Subscription #{self.pk} for User #{self.user_id} ({self.status})"


class Payment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="payments",
    )
    plan = models.ForeignKey(
        Plan,
        on_delete=models.PROTECT,
        related_name="payments",
    )
    subscription = models.OneToOneField(
        Subscription,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payment",
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    provider = models.CharField(max_length=30, default="robokassa")
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(
                fields=("user", "status"),
                name="sub_payment_user_status_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=PAYMENT_STATUS_VALUES),
                name="subscriptions_payment_status_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(amount__gte=Decimal("0.00")),
                name="subscriptions_payment_amount_non_negative",
            ),
        ]

    def __str__(self) -> str:
        return f"Payment #{self.pk} ({self.amount} RUB, {self.status})"
