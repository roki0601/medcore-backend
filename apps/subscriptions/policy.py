from __future__ import annotations

from typing import Any

from django.utils import timezone

from .selectors import get_active_subscription


def has_paid_content_entitlement(user: Any) -> bool:
    """Return whether ``user`` holds an active entitlement for paid content.

    ADR 0007 / BE-005:
    Access to ``paid`` topics requires an authenticated user with an active,
    unexpired subscription (or a cancelled subscription whose paid period has
    not yet ended). In MVP, any active plan grants paid content entitlement.
    Editor/Admin roles alone do not grant paid access.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if not getattr(user, "is_active", True):
        return False

    return get_active_subscription(user, at_time=timezone.now()) is not None
