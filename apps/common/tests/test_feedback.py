from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.common.models import Feedback
from apps.content.models import Section, Subject, Topic

User = get_user_model()


@pytest.fixture(autouse=True)
def clear_throttle_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def topic(db):
    subject = Subject.objects.create(
        title="Микробиология",
        slug="mikrobiologiya",
        position=1,
    )
    section = Section.objects.create(
        subject=subject,
        title="Общая микробиология",
        slug="obshchaya",
        position=1,
    )
    return Topic.objects.create(
        section=section,
        title="Ультраструктура бактерий",
        slug="ultrastruktura-bakteriy",
        status="published",
        position=1,
    )


@pytest.mark.django_db
def test_anonymous_feedback_creation(topic):
    client = APIClient()
    payload = {
        "type": "content_error",
        "subject": " Ошибка в формуле ",
        "message": "В разделе про УФ неправильно отображается формула.",
        "contact": "@student",
        "topic_id": topic.id,
        "page_url": "/mikrobiologiya/ultrastruktura-bakteriy",
    }

    response = client.post("/api/v1/feedback/", payload, format="json")
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["status"] == "new"
    assert "created_at" in data

    feedback = Feedback.objects.get(pk=data["id"])
    assert feedback.user is None
    assert feedback.type == "content_error"
    assert feedback.subject == "Ошибка в формуле"
    assert feedback.message == "В разделе про УФ неправильно отображается формула."
    assert feedback.contact == "@student"
    assert feedback.page_url == "/mikrobiologiya/ultrastruktura-bakteriy"
    assert feedback.topic == topic
    assert feedback.status == "new"


@pytest.mark.django_db
def test_authenticated_feedback_binds_request_user(topic):
    user = User.objects.create_user(username="testuser", password="password123")
    client = APIClient()
    client.force_authenticate(user=user)

    payload = {
        "type": "new_topic",
        "subject": "Добавьте тему по вирусам",
        "message": "Очень ждём тему по герпесвирусам и их репликации.",
        "user_id": 9999,  # Must be ignored by backend
    }

    response = client.post("/api/v1/feedback/", payload, format="json")
    assert response.status_code == 201

    feedback = Feedback.objects.get(pk=response.json()["id"])
    assert feedback.user == user
    assert feedback.type == "new_topic"
    assert feedback.topic is None
    assert feedback.contact == ""


@pytest.mark.django_db
def test_invalid_type_rejected():
    client = APIClient()
    payload = {
        "type": "invalid_type",
        "subject": "Тема",
        "message": "Сообщение длиннее 5 символов",
    }
    response = client.post("/api/v1/feedback/", payload, format="json")
    assert response.status_code == 400
    assert "type" in response.json()["fields"]


@pytest.mark.django_db
def test_empty_or_whitespace_subject_rejected():
    client = APIClient()
    payload = {
        "type": "other",
        "subject": "   ",
        "message": "Сообщение длиннее 5 символов",
    }
    response = client.post("/api/v1/feedback/", payload, format="json")
    assert response.status_code == 400
    assert "subject" in response.json()["fields"]


@pytest.mark.django_db
def test_message_validation():
    client = APIClient()
    # Too short (< 5 chars)
    response = client.post(
        "/api/v1/feedback/",
        {"type": "other", "subject": "Тема", "message": "1234"},
        format="json",
    )
    assert response.status_code == 400
    assert "message" in response.json()["fields"]

    # Whitespace only
    response = client.post(
        "/api/v1/feedback/",
        {"type": "other", "subject": "Тема", "message": "      "},
        format="json",
    )
    assert response.status_code == 400
    assert "message" in response.json()["fields"]

    # Too long (> 5000 chars)
    response = client.post(
        "/api/v1/feedback/",
        {"type": "other", "subject": "Тема", "message": "a" * 5001},
        format="json",
    )
    assert response.status_code == 400
    assert "message" in response.json()["fields"]


@pytest.mark.django_db
def test_invalid_topic_id_rejected():
    client = APIClient()
    payload = {
        "type": "content_error",
        "subject": "Тема",
        "message": "Сообщение длиннее 5 символов",
        "topic_id": 999999,
    }
    response = client.post("/api/v1/feedback/", payload, format="json")
    assert response.status_code == 400
    assert "topic_id" in response.json()["fields"]


@pytest.mark.django_db
def test_topic_deletion_sets_null_on_feedback(topic):
    feedback = Feedback.objects.create(
        type=Feedback.Type.CONTENT_ERROR,
        subject="Ошибка",
        message="Какое-то сообщение",
        topic=topic,
    )
    assert feedback.topic == topic

    topic.delete()
    feedback.refresh_from_db()
    assert feedback.topic is None


@pytest.mark.django_db
def test_html_and_script_stored_as_plain_text():
    client = APIClient()
    xss_payload = "<script>alert('xss')</script>"
    response = client.post(
        "/api/v1/feedback/",
        {
            "type": "technical_issue",
            "subject": xss_payload,
            "message": xss_payload,
            "contact": xss_payload,
        },
        format="json",
    )
    assert response.status_code == 201

    feedback = Feedback.objects.get(pk=response.json()["id"])
    assert feedback.subject == xss_payload
    assert feedback.message == xss_payload
    assert feedback.contact == xss_payload


@pytest.mark.django_db
def test_anonymous_rate_limit():
    client = APIClient()
    payload = {
        "type": "other",
        "subject": "Тест лимита",
        "message": "Сообщение для проверки рейт-лимита",
    }

    statuses = []
    for _ in range(6):
        statuses.append(
            client.post("/api/v1/feedback/", payload, format="json").status_code
        )

    assert statuses[:5] == [201] * 5
    assert statuses[5] == 429


@pytest.mark.django_db
def test_authenticated_rate_limit():
    user = User.objects.create_user(username="auth_limit_user", password="password123")
    client = APIClient()
    client.force_authenticate(user=user)

    payload = {
        "type": "suggestion",
        "subject": "Идея",
        "message": "Предложение по улучшению интерфейса платформы",
    }

    statuses = []
    for _ in range(11):
        statuses.append(
            client.post("/api/v1/feedback/", payload, format="json").status_code
        )

    assert statuses[:10] == [201] * 10
    assert statuses[10] == 429


@pytest.mark.django_db
def test_feedback_admin_actions():
    from django.contrib.admin.sites import AdminSite

    from apps.common.admin import FeedbackAdmin

    feedback1 = Feedback.objects.create(
        type=Feedback.Type.SUGGESTION,
        subject="Идея 1",
        message="Сообщение 1",
        status=Feedback.Status.NEW,
    )
    feedback2 = Feedback.objects.create(
        type=Feedback.Type.SUGGESTION,
        subject="Идея 2",
        message="Сообщение 2",
        status=Feedback.Status.NEW,
    )

    admin_instance = FeedbackAdmin(Feedback, AdminSite())

    admin_instance.mark_reviewed(None, Feedback.objects.filter(pk=feedback1.pk))
    feedback1.refresh_from_db()
    assert feedback1.status == Feedback.Status.REVIEWED

    admin_instance.mark_resolved(None, Feedback.objects.filter(pk=feedback2.pk))
    feedback2.refresh_from_db()
    assert feedback2.status == Feedback.Status.RESOLVED
