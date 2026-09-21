from __future__ import annotations

from dataclasses import dataclass

from apps.common.exceptions import APIError
from apps.content.access import evaluate_topic_access
from apps.content.models import ContentBlock, Subject, Topic
from apps.media.models import MediaFile
from apps.subscriptions.policy import has_paid_content_entitlement


@dataclass(frozen=True)
class MediaAccessDecision:
    """Outcome of the content-owned decision about one media row."""

    allowed: bool
    requires_authentication: bool


def decide_media_access(media: MediaFile, actor) -> MediaAccessDecision:
    """Decide whether ``actor`` may read the bytes behind ``media``.

    The decision is content-owned because media has no access semantics of its
    own: it is derived from the published content that references the file. Every
    published ``ContentBlock`` pointing at this media inside a published Topic is
    evaluated with the feature 002 access composition
    (:func:`apps.content.access.evaluate_topic_access`); the file is readable when
    any reference grants full access, or when the actor's demo-preview access
    meets a published ``is_demo_preview`` block.

    ``apps.media`` reaches this function through
    ``settings.MEDIA_ACCESS_POLICY_PROVIDER`` (resolved with ``import_string``),
    so ``media`` never imports ``content``. A missing provider denies the access.

    When nothing grants access the result distinguishes the two client outcomes:
    an unauthenticated actor is asked to authenticate (``requires_authentication``)
    while an authenticated actor is simply denied.
    """

    if (
        Subject.objects.filter(cover=media).exists()
        or Topic.objects.filter(
            cover=media,
            status=Topic.Status.PUBLISHED,
        ).exists()
    ):
        return MediaAccessDecision(allowed=True, requires_authentication=False)

    blocks = (
        ContentBlock.objects.filter(
            media=media,
            status=ContentBlock.Status.PUBLISHED,
            topic__status=Topic.Status.PUBLISHED,
        )
        .select_related("topic")
        .order_by("id")
    )
    entitled: bool | None = None
    for block in blocks:
        if block.topic.access_level == Topic.AccessLevel.PAID and entitled is None:
            entitled = has_paid_content_entitlement(actor)
        decision = evaluate_topic_access(block.topic, actor, entitled=entitled)
        if decision.full_access:
            return MediaAccessDecision(allowed=True, requires_authentication=False)
        if decision.is_demo_preview and block.is_demo_preview:
            return MediaAccessDecision(allowed=True, requires_authentication=False)

    authenticated = bool(actor is not None and actor.is_authenticated)
    return MediaAccessDecision(
        allowed=False,
        requires_authentication=not authenticated,
    )


def guard_media_deletion(media: MediaFile) -> None:
    """Refuse deleting media that published content still references.

    ``ContentBlock.media`` stays ``on_delete=SET_NULL``, so the database does not
    reject the deletion; this guard is the application-level protection. It runs
    inside the caller's transaction and locks the published referencing blocks,
    so a concurrent publish of a new reference serializes against the delete
    instead of slipping past the check. The repair path is detaching the
    reference first (``PATCH /api/v1/content/blocks/{id}/ {"media": null}``).

    ``apps.media`` reaches this function through
    ``settings.MEDIA_DELETE_GUARD_PROVIDER`` (resolved with ``import_string``),
    so ``media`` never imports ``content``. A missing provider refuses deletion.
    """

    published_reference = (
        ContentBlock.objects.select_for_update()
        .filter(media=media, status=ContentBlock.Status.PUBLISHED)
        .exists()
        or Subject.objects.select_for_update().filter(cover=media).exists()
        or Topic.objects.select_for_update().filter(cover=media).exists()
    )
    if published_reference:
        raise APIError(
            "Media is referenced by published content.",
            code="CONTENT_CONFLICT",
            status_code=409,
        )
