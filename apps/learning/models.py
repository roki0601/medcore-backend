from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.content.models import ContentBlock, Flashcard, Quiz, Topic

TOPIC_PROGRESS_STATUS_VALUES = ("not_started", "learning", "learned")
QUIZ_ATTEMPT_STATUS_VALUES = ("active", "submitted")


class UserTopicProgress(models.Model):
    """Current progress of one user in one topic.

    Derived values (theory percentage, completed/total block counts) are never
    stored; they are computed from ``UserTopicBlockProgress`` and the topic's
    published blocks.
    """

    class Status(models.TextChoices):
        NOT_STARTED = "not_started", "Not started"
        LEARNING = "learning", "Learning"
        LEARNED = "learned", "Learned"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="topic_progress",
    )
    topic = models.ForeignKey(
        Topic,
        on_delete=models.CASCADE,
        related_name="user_progress",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.NOT_STARTED,
    )
    last_opened_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("id",)
        constraints = [
            models.UniqueConstraint(
                fields=("user", "topic"),
                name="learning_usertopicprogress_unique_user_topic",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=TOPIC_PROGRESS_STATUS_VALUES),
                name="learning_usertopicprogress_status_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"UserTopicProgress {self.pk}"


class UserTopicBlockProgress(models.Model):
    """Explicit completion of one theory block by one user.

    There is deliberately no ``topic`` column: the content API can re-parent a
    block to another topic, so a stored ``(topic, block)`` pair could go stale.
    The topic is always derived from ``block.topic``.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="topic_block_progress",
    )
    block = models.ForeignKey(
        ContentBlock,
        on_delete=models.CASCADE,
        related_name="user_progress",
    )
    is_complete = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("id",)
        constraints = [
            models.UniqueConstraint(
                fields=("user", "block"),
                name="learning_usertopicblockprogress_unique_user_block",
            ),
        ]

    def __str__(self) -> str:
        return f"UserTopicBlockProgress {self.pk}"


class FlashcardReview(models.Model):
    """Current scheduler state of one user for one flashcard.

    One current row per user/card: ``know`` and ``repeat`` update this row
    instead of appending review history.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="flashcard_reviews",
    )
    flashcard = models.ForeignKey(
        Flashcard,
        on_delete=models.CASCADE,
        related_name="reviews",
    )
    interval_days = models.PositiveIntegerField(default=0)
    repetitions = models.PositiveIntegerField(default=0)
    last_reviewed_at = models.DateTimeField(null=True, blank=True)
    next_review_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("id",)
        constraints = [
            models.UniqueConstraint(
                fields=("user", "flashcard"),
                name="learning_flashcardreview_unique_user_flashcard",
            ),
        ]
        indexes = [
            # Django caps index names at 30 characters (models.E034); the
            # ``data-model.md`` name is longer than that limit allows.
            models.Index(
                fields=("user", "next_review_at"),
                name="learning_fcreview_due_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"FlashcardReview {self.pk}"


class QuizAttempt(models.Model):
    """One started/submitted attempt of one user on one quiz.

    ``answers_state`` holds answer IDs only; the frozen question set and the
    graded breakdown live in their own fields. There is no ``passed`` column and
    no pass threshold: the owner decision on a global pass percentage is still
    open, so submit stores only ``score_percent`` and the per-question results.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        SUBMITTED = "submitted", "Submitted"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="quiz_attempts",
    )
    quiz = models.ForeignKey(
        Quiz,
        on_delete=models.CASCADE,
        related_name="attempts",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    answers_state = models.JSONField(default=dict)
    question_ids = models.JSONField(default=list)
    results = models.JSONField(null=True, blank=True)
    score_percent = models.PositiveSmallIntegerField(null=True, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("id",)
        constraints = [
            models.UniqueConstraint(
                fields=("user", "quiz"),
                condition=models.Q(status="active"),
                name="learning_quizattempt_unique_active_user_quiz",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=QUIZ_ATTEMPT_STATUS_VALUES),
                name="learning_quizattempt_status_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(score_percent__isnull=True)
                | models.Q(score_percent__gte=0, score_percent__lte=100),
                name="learning_quizattempt_score_bounds",
            ),
        ]
        indexes = [
            models.Index(
                fields=("user", "quiz", "status"),
                name="learning_quizattempt_quiz_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"QuizAttempt {self.pk}"
