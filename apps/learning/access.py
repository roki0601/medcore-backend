"""Published-topic access resolution for the learning API (feature 003).

Every learning route re-checks the published topic and the ``content`` access
decision, so learning state is never exposed for a missing, unpublished or
unentitled topic. ``learning`` consumes the decision composed by
``apps.content.access`` and never reads subscription state itself.
"""

from __future__ import annotations

from apps.common.exceptions import APIError
from apps.content.access import evaluate_topic_access
from apps.content.models import Flashcard, Quiz, Topic
from apps.content.selectors import get_published_topic


def _not_found() -> APIError:
    return APIError("Resource not found.", code="RESOURCE_NOT_FOUND", status_code=404)


def _require_published_topic(topic_id: int) -> Topic:
    topic = get_published_topic(topic_id)
    if topic is None:
        raise _not_found()
    return topic


def require_topic_access(topic: Topic, user) -> Topic:
    """Return ``topic`` when the actor may read it, else raise 403.

    A missing or unpublished topic is 404 before this check; an authenticated
    actor without an active paid entitlement is 403
    ``TOPIC_ENTITLEMENT_REQUIRED``.
    """

    if not evaluate_topic_access(topic, user).full_access:
        raise APIError(
            "An active entitlement is required for this paid topic.",
            code="TOPIC_ENTITLEMENT_REQUIRED",
            status_code=403,
        )
    return topic


def get_accessible_published_topic(topic_id: int, user) -> Topic:
    """Resolve one published, accessible Topic or raise 404/403."""

    return require_topic_access(_require_published_topic(topic_id), user)


def get_accessible_flashcard(flashcard_id: int, user) -> Flashcard:
    """Resolve one Flashcard of a published, accessible Topic or raise 404/403."""

    flashcard = (
        Flashcard.objects.select_related("topic").filter(pk=flashcard_id).first()
    )
    if flashcard is None:
        raise _not_found()
    require_topic_access(_require_published_topic(flashcard.topic_id), user)
    return flashcard


def get_accessible_quiz(quiz_id: int, user) -> Quiz:
    """Resolve one Quiz of a published, accessible Topic or raise 404/403."""

    quiz = Quiz.objects.select_related("topic").filter(pk=quiz_id).first()
    if quiz is None:
        raise _not_found()
    require_topic_access(_require_published_topic(quiz.topic_id), user)
    return quiz
