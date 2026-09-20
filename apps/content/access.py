from __future__ import annotations

from dataclasses import dataclass

from apps.common.exceptions import APIError
from apps.content.models import ContentBlock, Topic
from apps.content.selectors import topic_content_blocks
from apps.subscriptions.policy import has_paid_content_entitlement


@dataclass(frozen=True)
class TopicAccessDecision:
    level: str
    full_access: bool
    is_demo_preview: bool


def evaluate_topic_access(
    topic: Topic,
    user,
    *,
    entitled: bool | None = None,
) -> TopicAccessDecision:
    """Compose the ADR 0007 access matrix for one published Topic.

    ``content`` owns this composition and reads entitlement only through the
    public subscriptions policy boundary; it never inspects Subscription state.
    When ``entitled`` is explicitly provided, it avoids redundant subscription
    lookups when evaluating multiple topics in batch.
    """

    authenticated = bool(user is not None and user.is_authenticated)
    level = topic.access_level
    if level == Topic.AccessLevel.DEMO:
        return TopicAccessDecision(level=level, full_access=True, is_demo_preview=False)
    if not authenticated:
        return TopicAccessDecision(level=level, full_access=False, is_demo_preview=True)
    if level == Topic.AccessLevel.FREE:
        return TopicAccessDecision(level=level, full_access=True, is_demo_preview=False)
    if entitled is None:
        entitled = has_paid_content_entitlement(user)
    return TopicAccessDecision(
        level=level,
        full_access=bool(entitled),
        is_demo_preview=False,
    )


def resolve_topic_blocks(
    topic: Topic,
    user,
) -> tuple[TopicAccessDecision, list[ContentBlock]]:
    """Return the access decision and the blocks the actor may read.

    Anonymous actors on a free/paid topic receive the published demo-preview
    subset; when none exists the full body requires authentication. An
    authenticated actor without a paid entitlement is denied.
    """

    decision = evaluate_topic_access(topic, user)
    if decision.full_access:
        return decision, topic_content_blocks(topic, preview_only=False)
    if decision.is_demo_preview:
        preview = topic_content_blocks(topic, preview_only=True)
        if preview:
            return decision, preview
        raise APIError(
            "Authentication is required to read this topic.",
            code="AUTHENTICATION_REQUIRED",
            status_code=401,
        )
    raise APIError(
        "An active entitlement is required for this paid topic.",
        code="TOPIC_ENTITLEMENT_REQUIRED",
        status_code=403,
    )
