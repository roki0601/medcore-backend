from __future__ import annotations

from apps.users.models import User


def has_paid_content_entitlement(user: User) -> bool:
    """Return whether ``user`` holds an active entitlement for paid content.

    ADR 0007 grants ``paid`` Topic access only for an active
    entitlement/subscription. The subscription and entitlement lifecycle is a
    separate feature that is not implemented yet, so no entitlement source
    exists and the honest current answer is ``False`` for every user. Content
    and learning must resolve paid access only through this boundary and never
    read Subscription state directly; the subscriptions feature replaces this
    body without changing the content contract.
    """

    del user
    return False
