from __future__ import annotations

from django.conf import settings
from django.db import models


class Feedback(models.Model):
    class Type(models.TextChoices):
        CONTENT_ERROR = "content_error", "Ошибка в материале"
        NEW_TOPIC = "new_topic", "Предложить тему"
        NEW_SUBJECT = "new_subject", "Предложить предмет"
        SUGGESTION = "suggestion", "Идея / пожелание"
        TECHNICAL_ISSUE = "technical_issue", "Техническая проблема"
        OTHER = "other", "Другое"

    class Status(models.TextChoices):
        NEW = "new", "Новое"
        REVIEWED = "reviewed", "На рассмотрении"
        RESOLVED = "resolved", "Решено"
        REJECTED = "rejected", "Отклонено"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="feedbacks",
    )
    type = models.CharField(
        max_length=50,
        choices=Type.choices,
        default=Type.OTHER,
        db_index=True,
    )
    subject = models.CharField(max_length=255)
    message = models.TextField()
    contact = models.CharField(max_length=255, blank=True, default="")
    page_url = models.CharField(max_length=500, blank=True, default="")
    topic = models.ForeignKey(
        "content.Topic",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="feedbacks",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NEW,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"Feedback #{self.pk} [{self.type}]: {self.subject}"
