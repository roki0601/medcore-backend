"""Tests for user profile and study preferences API (BE-008)."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.content.access import evaluate_topic_access
from apps.content.models import Section, Subject, Topic
from apps.users.models import UserProfile

User = get_user_model()


@pytest.fixture
def subject_anatomy(db) -> Subject:
    return Subject.objects.create(
        title="Анатомия",
        slug="anatomy",
        position=1,
    )


@pytest.fixture
def subject_physiology(db) -> Subject:
    return Subject.objects.create(
        title="Нормальная физиология",
        slug="physiology",
        position=2,
    )


@pytest.fixture
def subject_microbiology(db) -> Subject:
    return Subject.objects.create(
        title="Микробиология",
        slug="microbiology",
        position=3,
    )


@pytest.mark.django_db
def test_anonymous_get_returns_401(api_client):
    """1. Anonymous GET /api/v1/profile/ returns 401."""
    response = api_client.get("/api/v1/profile/")
    assert response.status_code == 401
    data = response.json()
    assert data["code"] == "AUTHENTICATION_REQUIRED"


@pytest.mark.django_db
def test_anonymous_patch_returns_401(api_client):
    """2. Anonymous PATCH /api/v1/profile/ returns 401."""
    response = api_client.patch(
        "/api/v1/profile/",
        {"university": "БашГМУ"},
        format="json",
    )
    assert response.status_code == 401
    data = response.json()
    assert data["code"] == "AUTHENTICATION_REQUIRED"


@pytest.mark.django_db
def test_authenticated_user_without_profile_returns_empty_profile(
    api_client, make_user, authenticate
):
    """3. User without existing profile row gets canonical empty profile."""
    user = make_user(username="student1")
    client = authenticate(api_client, user)

    # Ensure profile row didn't exist before request
    assert not UserProfile.objects.filter(user=user).exists()

    response = client.get("/api/v1/profile/")
    assert response.status_code == 200
    data = response.json()
    assert data == {
        "university": "",
        "course": None,
        "semester_goal": "",
        "daily_study_minutes": None,
        "selected_subjects": [],
    }
    # Row is safely created
    assert UserProfile.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_patch_creates_and_updates_profile(
    api_client, make_user, authenticate, subject_anatomy
):
    """4. PATCH creates/updates profile fields."""
    user = make_user(username="student2")
    client = authenticate(api_client, user)

    payload = {
        "university": "БашГМУ",
        "course": 4,
        "semester_goal": "Закрыть микробиологию и патфиз",
        "daily_study_minutes": 60,
        "selected_subject_ids": [subject_anatomy.id],
    }
    response = client.patch("/api/v1/profile/", payload, format="json")
    assert response.status_code == 200
    data = response.json()
    assert data["university"] == "БашГМУ"
    assert data["course"] == 4
    assert data["semester_goal"] == "Закрыть микробиологию и патфиз"
    assert data["daily_study_minutes"] == 60
    assert len(data["selected_subjects"]) == 1
    assert data["selected_subjects"][0]["id"] == subject_anatomy.id
    assert data["selected_subjects"][0]["title"] == "Анатомия"
    assert data["selected_subjects"][0]["slug"] == "anatomy"


@pytest.mark.django_db
def test_partial_patch_preserves_other_fields(
    api_client, make_user, authenticate, subject_anatomy
):
    """5. Partial PATCH does not wipe omitted fields."""
    user = make_user(username="student3")
    client = authenticate(api_client, user)

    # Initial setup
    client.patch(
        "/api/v1/profile/",
        {
            "university": "Сеченовский Университет",
            "course": 3,
            "semester_goal": "Сдать гистологию",
            "daily_study_minutes": 90,
            "selected_subject_ids": [subject_anatomy.id],
        },
        format="json",
    )

    # Partial update: only daily_study_minutes
    response = client.patch(
        "/api/v1/profile/",
        {"daily_study_minutes": 120},
        format="json",
    )
    assert response.status_code == 200
    data = response.json()
    assert data["university"] == "Сеченовский Университет"
    assert data["course"] == 3
    assert data["semester_goal"] == "Сдать гистологию"
    assert data["daily_study_minutes"] == 120
    assert len(data["selected_subjects"]) == 1
    assert data["selected_subjects"][0]["id"] == subject_anatomy.id


@pytest.mark.django_db
def test_course_less_than_1_rejected(api_client, make_user, authenticate):
    """6. course < 1 is rejected."""
    user = make_user(username="student4")
    client = authenticate(api_client, user)

    response = client.patch(
        "/api/v1/profile/",
        {"course": 0},
        format="json",
    )
    assert response.status_code == 400
    data = response.json()
    assert data["code"] == "INVALID_REQUEST"
    assert "course" in data["fields"]


@pytest.mark.django_db
def test_course_greater_than_6_rejected(api_client, make_user, authenticate):
    """7. course > 6 is rejected."""
    user = make_user(username="student5")
    client = authenticate(api_client, user)

    response = client.patch(
        "/api/v1/profile/",
        {"course": 7},
        format="json",
    )
    assert response.status_code == 400
    data = response.json()
    assert data["code"] == "INVALID_REQUEST"
    assert "course" in data["fields"]


@pytest.mark.django_db
def test_invalid_daily_study_minutes_rejected(api_client, make_user, authenticate):
    """8. daily_study_minutes < 1 or > 1440 is rejected."""
    user = make_user(username="student6")
    client = authenticate(api_client, user)

    response_low = client.patch(
        "/api/v1/profile/",
        {"daily_study_minutes": 0},
        format="json",
    )
    assert response_low.status_code == 400
    assert response_low.json()["code"] == "INVALID_REQUEST"
    assert "daily_study_minutes" in response_low.json()["fields"]

    response_high = client.patch(
        "/api/v1/profile/",
        {"daily_study_minutes": 1441},
        format="json",
    )
    assert response_high.status_code == 400
    assert response_high.json()["code"] == "INVALID_REQUEST"
    assert "daily_study_minutes" in response_high.json()["fields"]


@pytest.mark.django_db
def test_selected_subjects_persisted(
    api_client, make_user, authenticate, subject_anatomy, subject_physiology
):
    """9. selected_subjects are persisted."""
    user = make_user(username="student7")
    client = authenticate(api_client, user)

    response = client.patch(
        "/api/v1/profile/",
        {"selected_subject_ids": [subject_anatomy.id, subject_physiology.id]},
        format="json",
    )
    assert response.status_code == 200
    retrieved = client.get("/api/v1/profile/")
    assert retrieved.status_code == 200
    subject_ids = {s["id"] for s in retrieved.json()["selected_subjects"]}
    assert subject_ids == {subject_anatomy.id, subject_physiology.id}


@pytest.mark.django_db
def test_repeated_patch_selected_subjects_replaces_set(
    api_client,
    make_user,
    authenticate,
    subject_anatomy,
    subject_physiology,
    subject_microbiology,
):
    """10. Repeated PATCH selected_subjects replaces the full set."""
    user = make_user(username="student8")
    client = authenticate(api_client, user)

    # Initially [anatomy, physiology]
    client.patch(
        "/api/v1/profile/",
        {"selected_subject_ids": [subject_anatomy.id, subject_physiology.id]},
        format="json",
    )

    # Replace with [microbiology]
    response = client.patch(
        "/api/v1/profile/",
        {"selected_subject_ids": [subject_microbiology.id]},
        format="json",
    )
    assert response.status_code == 200
    subject_ids = [s["id"] for s in response.json()["selected_subjects"]]
    assert subject_ids == [subject_microbiology.id]

    # Replace with [] (empty)
    response_empty = client.patch(
        "/api/v1/profile/",
        {"selected_subject_ids": []},
        format="json",
    )
    assert response_empty.status_code == 200
    assert response_empty.json()["selected_subjects"] == []


@pytest.mark.django_db
def test_unknown_subject_rejected(api_client, make_user, authenticate, subject_anatomy):
    """11. Unknown Subject id is rejected with canonical validation error."""
    user = make_user(username="student9")
    client = authenticate(api_client, user)

    response = client.patch(
        "/api/v1/profile/",
        {"selected_subject_ids": [subject_anatomy.id, 999999]},
        format="json",
    )
    assert response.status_code == 400
    data = response.json()
    assert data["code"] == "INVALID_REQUEST"
    assert "selected_subjects" in data["fields"]


@pytest.mark.django_db
def test_selected_subject_aliases_cannot_be_sent_together(
    api_client, make_user, authenticate, subject_anatomy
):
    """Conflicting subject field aliases are rejected without a partial update."""
    user = make_user(username="ambiguous_subjects")
    client = authenticate(api_client, user)

    response = client.patch(
        "/api/v1/profile/",
        {
            "selected_subject_ids": [subject_anatomy.id],
            "selected_subjects": [],
        },
        format="json",
    )

    assert response.status_code == 400
    data = response.json()
    assert data["code"] == "INVALID_REQUEST"
    assert data["fields"] == {
        "selected_subject_ids": ["Send only one subject selection field."],
        "selected_subjects": ["Send only one subject selection field."],
    }
    assert not UserProfile.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_other_user_cannot_read_or_modify_profile(api_client, make_user, authenticate):
    """12. Each user sees only their own private profile; cannot modify other's."""
    user_alice = make_user(username="alice")
    user_bob = make_user(username="bob")

    client_alice = authenticate(api_client, user_alice)
    client_alice.patch(
        "/api/v1/profile/",
        {"university": "Alice Med Uni", "course": 2},
        format="json",
    )

    client_bob = authenticate(APIClient(), user_bob)
    bob_profile = client_bob.get("/api/v1/profile/").json()
    assert bob_profile["university"] == ""
    assert bob_profile["course"] is None

    # Bob patches his profile
    client_bob.patch(
        "/api/v1/profile/",
        {"university": "Bob Med Academy", "course": 5},
        format="json",
    )

    # Alice's profile is untouched
    alice_profile = client_alice.get("/api/v1/profile/").json()
    assert alice_profile["university"] == "Alice Med Uni"
    assert alice_profile["course"] == 2


@pytest.mark.django_db
def test_user_deletion_cascades_to_profile_preserving_subjects(
    make_user, subject_anatomy
):
    """13. User deletion CASCADE deletes UserProfile without touching Subject."""
    user = make_user(username="to_delete")
    profile = UserProfile.objects.create(
        user=user,
        university="Test Uni",
        course=1,
    )
    profile.selected_subjects.add(subject_anatomy)
    profile_id = profile.id
    subject_id = subject_anatomy.id

    user.delete()

    assert not UserProfile.objects.filter(id=profile_id).exists()
    assert Subject.objects.filter(id=subject_id).exists()


@pytest.mark.django_db
def test_selected_subjects_do_not_affect_content_access(
    make_user, subject_anatomy, subject_physiology
):
    """14. selected_subjects does not alter content access evaluation."""
    user = make_user(username="content_tester")

    section = Section.objects.create(
        subject=subject_anatomy,
        title="Введение",
        slug="intro",
        position=1,
    )
    demo_topic = Topic.objects.create(
        section=section,
        title="Демо тема",
        slug="demo-topic",
        position=1,
        access_level=Topic.AccessLevel.DEMO,
        status=Topic.Status.PUBLISHED,
    )
    free_topic = Topic.objects.create(
        section=section,
        title="Бесплатная тема",
        slug="free-topic",
        position=2,
        access_level=Topic.AccessLevel.FREE,
        status=Topic.Status.PUBLISHED,
    )
    paid_topic = Topic.objects.create(
        section=section,
        title="Платная тема",
        slug="paid-topic",
        position=3,
        access_level=Topic.AccessLevel.PAID,
        status=Topic.Status.PUBLISHED,
    )

    # Without any selected subjects
    assert evaluate_topic_access(demo_topic, user).full_access is True
    assert evaluate_topic_access(free_topic, user).full_access is True
    assert evaluate_topic_access(paid_topic, user).full_access is False

    # Now user selects an unrelated subject
    profile = UserProfile.objects.create(user=user)
    profile.selected_subjects.add(subject_physiology)

    # Access remains completely unchanged
    assert evaluate_topic_access(demo_topic, user).full_access is True
    assert evaluate_topic_access(free_topic, user).full_access is True
    assert evaluate_topic_access(paid_topic, user).full_access is False

    # Now user selects the topic's subject
    profile.selected_subjects.add(subject_anatomy)

    # Access is strictly determined by topic level and subscription
    assert evaluate_topic_access(demo_topic, user).full_access is True
    assert evaluate_topic_access(free_topic, user).full_access is True
    assert evaluate_topic_access(paid_topic, user).full_access is False


@pytest.mark.django_db
def test_auth_and_telegram_fields_cannot_be_changed_via_profile(
    api_client, make_user, authenticate
):
    """15. Telegram and auth identity fields cannot be changed via profile endpoint."""
    user = make_user(username="original_user", role=User.Role.USER)
    user.telegram_id = 111222333
    user.save()

    client = authenticate(api_client, user)

    forbidden_payloads = [
        {"telegram_id": 999888777},
        {"telegram_username": "hacker"},
        {"username": "new_username"},
        {"role": "admin"},
        {"is_staff": True},
        {"is_superuser": True},
        {"auth_version": 99},
        {"subscription": "premium"},
        {"progress": 100},
    ]

    for payload in forbidden_payloads:
        response = client.patch("/api/v1/profile/", payload, format="json")
        assert response.status_code == 400
        data = response.json()
        assert data["code"] == "INVALID_REQUEST"
        assert "unknown" in data["fields"]

    user.refresh_from_db()
    assert user.username == "original_user"
    assert user.telegram_id == 111222333
    assert user.role == User.Role.USER
    assert user.is_staff is False
    assert user.is_superuser is False
    assert user.auth_version == 0


@pytest.mark.django_db
def test_openapi_schema_contains_profile_endpoints(api_client):
    """16. OpenAPI schema documents GET and PATCH /api/v1/profile/."""
    response = api_client.get("/api/v1/schema/", HTTP_ACCEPT="application/json")
    assert response.status_code == 200
    schema = response.json()

    assert "/api/v1/profile/" in schema["paths"]
    profile_path = schema["paths"]["/api/v1/profile/"]

    assert "get" in profile_path
    assert "patch" in profile_path

    # Security requires bearerAuth
    assert profile_path["get"]["security"] == [{"bearerAuth": []}]
    assert profile_path["patch"]["security"] == [{"bearerAuth": []}]

    # Responses
    get_responses = profile_path["get"]["responses"]
    assert "200" in get_responses
    assert "401" in get_responses

    patch_responses = profile_path["patch"]["responses"]
    assert "200" in patch_responses
    assert "400" in patch_responses
    assert "401" in patch_responses
