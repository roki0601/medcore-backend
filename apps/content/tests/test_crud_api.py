"""API tests for the 004 content CRUD surface under ``/api/v1/content/``."""

from __future__ import annotations

import pytest
from drf_spectacular.generators import SchemaGenerator
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken

from apps.content.models import (
    ContentBlock,
    Flashcard,
    Quiz,
    QuizAnswer,
    QuizQuestion,
    Section,
    Source,
    Subject,
    Topic,
)
from apps.media.models import MediaFile

SUBJECTS_URL = "/api/v1/content/subjects/"
SECTIONS_URL = "/api/v1/content/sections/"
TOPICS_URL = "/api/v1/content/topics/"
BLOCKS_URL = "/api/v1/content/blocks/"
FLASHCARDS_URL = "/api/v1/content/flashcards/"
QUIZZES_URL = "/api/v1/content/quizzes/"
SOURCES_URL = "/api/v1/content/sources/"

RESOURCES = (
    "subjects",
    "sections",
    "topics",
    "blocks",
    "flashcards",
    "quizzes",
    "sources",
)
CONTENT_PATHS = tuple(
    path
    for resource in RESOURCES
    for path in (
        f"/api/v1/content/{resource}/",
        f"/api/v1/content/{resource}/{{id}}/",
    )
)


def _detail(url: str, pk: int) -> str:
    return f"{url}{pk}/"


def _authorization(user) -> str:
    """A versioned access token for one user, as the JWT authenticator expects."""

    access = RefreshToken.for_user(user).access_token
    access["auth_version"] = user.auth_version
    return f"Bearer {access}"


def _question(text: str = "Which are beta-lactams?", *, correct: str = "Penicillin"):
    return {
        "text": text,
        "answers": [
            {"text": correct, "is_correct": True},
            {"text": "Gentamicin"},
        ],
    }


def _create_quiz(client, topic, questions, *, title: str = "Basics") -> dict:
    """Create a quiz through the API and return its detail representation."""

    created = client.post(
        QUIZZES_URL,
        {"topic": topic.pk, "title": title, "questions": questions},
        format="json",
    )
    assert created.status_code == 201
    detail = client.get(_detail(QUIZZES_URL, created.json()["id"]))
    assert detail.status_code == 200
    return detail.json()


@pytest.fixture
def topic(catalog) -> Topic:
    return catalog["add_topic"](
        title="Beta-lactams",
        slug="beta-lactams",
        position=1,
    )


@pytest.fixture
def media_file(db) -> MediaFile:
    return MediaFile.objects.create(
        storage_key="authoring/structure.png",
        original_name="structure.png",
        mime_type="image/png",
        size_bytes=2048,
    )


# ---------------------------------------------------------------------------
# 1. Integration key, editor/admin JWT and the user-facing boundary.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_integration_key_creates_then_upserts_with_201_and_200(integration_client):
    created = integration_client.post(
        SUBJECTS_URL,
        {"title": "Anatomy", "external_id": "anat-1"},
        format="json",
    )
    assert created.status_code == 201
    body = created.json()
    assert body["title"] == "Anatomy"
    assert body["external_id"] == "anat-1"

    updated = integration_client.post(
        SUBJECTS_URL,
        {"title": "Anatomy revised", "external_id": "anat-1"},
        format="json",
    )
    assert updated.status_code == 200
    assert updated.json()["id"] == body["id"]
    assert Subject.objects.count() == 1


@pytest.mark.django_db
def test_wrong_integration_key_is_rejected_alone_and_beside_a_valid_editor_jwt(
    api_client, editor
):
    api_client.credentials(HTTP_X_MEDCORE_INTEGRATION_KEY="wrong-key")
    alone = api_client.post(SUBJECTS_URL, {"title": "Anatomy"}, format="json")
    assert alone.status_code == 401
    assert alone.json()["code"] == "INTEGRATION_KEY_INVALID"

    api_client.credentials(
        HTTP_X_MEDCORE_INTEGRATION_KEY="wrong-key",
        HTTP_AUTHORIZATION=_authorization(editor),
    )
    beside_jwt = api_client.post(SUBJECTS_URL, {"title": "Anatomy"}, format="json")
    assert beside_jwt.status_code == 401
    assert beside_jwt.json()["code"] == "INTEGRATION_KEY_INVALID"
    assert not Subject.objects.exists()


@pytest.mark.django_db
def test_authoring_routes_require_credentials(api_client):
    response = api_client.post(SUBJECTS_URL, {"title": "Anatomy"}, format="json")

    assert response.status_code == 401
    assert response.json()["code"] == "AUTHENTICATION_REQUIRED"


@pytest.mark.django_db
def test_plain_user_jwt_is_denied(api_client, make_user):
    api_client.credentials(
        HTTP_AUTHORIZATION=_authorization(make_user(username="reader"))
    )
    response = api_client.post(SUBJECTS_URL, {"title": "Anatomy"}, format="json")

    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"
    assert not Subject.objects.exists()


@pytest.mark.django_db
def test_editor_and_admin_jwts_author_content(api_client, editor, admin_user):
    for user in (editor, admin_user):
        api_client.credentials(HTTP_AUTHORIZATION=_authorization(user))
        response = api_client.post(
            SUBJECTS_URL,
            {"title": f"Written by {user.username}"},
            format="json",
        )
        assert response.status_code == 201

    assert Subject.objects.count() == 2


@pytest.mark.django_db
def test_integration_key_never_authenticates_a_user_facing_route(
    integration_client, catalog
):
    topic = catalog["add_topic"](
        title="Free topic",
        slug="free-topic",
        position=1,
        access_level=Topic.AccessLevel.FREE,
    )

    content = integration_client.get(f"/api/v1/topics/{topic.pk}/content/")
    assert content.status_code == 401
    assert content.json()["code"] == "AUTHENTICATION_REQUIRED"

    account = integration_client.get("/api/v1/auth/me/")
    assert account.status_code == 401
    assert account.json()["code"] == "AUTHENTICATION_REQUIRED"


# ---------------------------------------------------------------------------
# 2. CRUD per resource: create, list, detail, patch, delete, repeated delete.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_subject_crud(integration_client):
    created = integration_client.post(
        SUBJECTS_URL,
        {"title": "Pharmacology", "position": 1},
        format="json",
    )
    assert created.status_code == 201
    pk = created.json()["id"]

    listed = integration_client.get(SUBJECTS_URL)
    assert [row["id"] for row in listed.json()["results"]] == [pk]

    detail = integration_client.get(_detail(SUBJECTS_URL, pk))
    assert detail.status_code == 200
    assert detail.json()["title"] == "Pharmacology"

    patched = integration_client.patch(
        _detail(SUBJECTS_URL, pk),
        {"title": "Pharmacology II"},
        format="json",
    )
    assert patched.status_code == 200
    assert patched.json()["title"] == "Pharmacology II"
    assert Subject.objects.get(pk=pk).title == "Pharmacology II"

    assert integration_client.delete(_detail(SUBJECTS_URL, pk)).status_code == 204
    assert not Subject.objects.filter(pk=pk).exists()

    repeated = integration_client.delete(_detail(SUBJECTS_URL, pk))
    assert repeated.status_code == 404
    assert repeated.json()["code"] == "RESOURCE_NOT_FOUND"

    unknown = _detail(SUBJECTS_URL, 999999)
    assert integration_client.get(unknown).status_code == 404
    assert (
        integration_client.patch(unknown, {"title": "Ghost"}, format="json").status_code
        == 404
    )
    assert integration_client.delete(unknown).status_code == 404


@pytest.mark.django_db
def test_section_crud(integration_client, catalog):
    subject = catalog["subject"]
    created = integration_client.post(
        SECTIONS_URL,
        {"subject": subject.pk, "title": "Antibiotics", "position": 2},
        format="json",
    )
    assert created.status_code == 201
    body = created.json()
    assert body["subject"] == subject.pk
    pk = body["id"]

    listed = integration_client.get(SECTIONS_URL)
    assert [row["id"] for row in listed.json()["results"]] == [
        catalog["section"].pk,
        pk,
    ]

    patched = integration_client.patch(
        _detail(SECTIONS_URL, pk),
        {"title": "Antibiotics II"},
        format="json",
    )
    assert patched.status_code == 200
    assert patched.json()["title"] == "Antibiotics II"
    assert Section.objects.get(pk=pk).subject_id == subject.pk

    detail = integration_client.get(_detail(SECTIONS_URL, pk))
    assert detail.status_code == 200
    assert detail.json()["title"] == "Antibiotics II"

    assert integration_client.delete(_detail(SECTIONS_URL, pk)).status_code == 204
    assert not Section.objects.filter(pk=pk).exists()
    assert integration_client.delete(_detail(SECTIONS_URL, pk)).status_code == 404
    assert integration_client.get(_detail(SECTIONS_URL, 999999)).status_code == 404


@pytest.mark.django_db
def test_topic_crud(integration_client, catalog):
    section = catalog["section"]
    created = integration_client.post(
        TOPICS_URL,
        {
            "section": section.pk,
            "title": "Macrolides",
            "position": 2,
            "status": "published",
            "access_level": "free",
        },
        format="json",
    )
    assert created.status_code == 201
    pk = created.json()["id"]

    detail = integration_client.get(_detail(TOPICS_URL, pk))
    assert detail.json()["status"] == "published"
    assert detail.json()["access_level"] == "free"
    assert detail.json()["section"] == section.pk

    patched = integration_client.patch(
        _detail(TOPICS_URL, pk),
        {"access_level": "paid"},
        format="json",
    )
    assert patched.status_code == 200
    assert patched.json()["access_level"] == "paid"
    assert patched.json()["title"] == "Macrolides"

    assert integration_client.delete(_detail(TOPICS_URL, pk)).status_code == 204
    assert not Topic.objects.filter(pk=pk).exists()
    assert integration_client.delete(_detail(TOPICS_URL, pk)).status_code == 404
    assert integration_client.get(_detail(TOPICS_URL, 999999)).status_code == 404


@pytest.mark.django_db
def test_topic_list_includes_drafts(integration_client, catalog):
    section = catalog["section"]
    for position, status in ((2, "draft"), (3, "published")):
        created = integration_client.post(
            TOPICS_URL,
            {
                "section": section.pk,
                "title": f"Topic {position}",
                "position": position,
                "status": status,
            },
            format="json",
        )
        assert created.status_code == 201

    listed = integration_client.get(TOPICS_URL).json()

    assert listed["count"] == 2
    assert [row["status"] for row in listed["results"]] == ["draft", "published"]


@pytest.mark.django_db
def test_block_crud(integration_client, topic, media_file):
    created = integration_client.post(
        BLOCKS_URL,
        {
            "topic": topic.pk,
            "block_type": "image",
            "position": 1,
            "media": media_file.pk,
            "caption": "Structure",
        },
        format="json",
    )
    assert created.status_code == 201
    body = created.json()
    assert body["block_type"] == "image"
    assert body["media"] == media_file.pk
    pk = body["id"]

    listed = integration_client.get(BLOCKS_URL).json()
    assert [row["id"] for row in listed["results"]] == [pk]
    assert listed["results"][0]["status"] == "draft"

    patched = integration_client.patch(
        _detail(BLOCKS_URL, pk),
        {"caption": "Structure of penicillin"},
        format="json",
    )
    assert patched.status_code == 200
    assert patched.json()["caption"] == "Structure of penicillin"
    assert patched.json()["media"] == media_file.pk

    detail = integration_client.get(_detail(BLOCKS_URL, pk))
    assert detail.status_code == 200
    assert detail.json()["block_type"] == "image"
    assert detail.json()["markdown_body"] == ""

    assert integration_client.delete(_detail(BLOCKS_URL, pk)).status_code == 204
    assert not ContentBlock.objects.filter(pk=pk).exists()
    assert integration_client.delete(_detail(BLOCKS_URL, pk)).status_code == 404
    assert integration_client.get(_detail(BLOCKS_URL, 999999)).status_code == 404


@pytest.mark.django_db
def test_flashcard_crud(integration_client, topic):
    created = integration_client.post(
        FLASHCARDS_URL,
        {
            "topic": topic.pk,
            "question": "Which ring is strained?",
            "answer": "Beta-lactam",
        },
        format="json",
    )
    assert created.status_code == 201
    pk = created.json()["id"]

    listed = integration_client.get(FLASHCARDS_URL).json()
    assert [row["id"] for row in listed["results"]] == [pk]

    patched = integration_client.patch(
        _detail(FLASHCARDS_URL, pk),
        {"answer": "The beta-lactam ring"},
        format="json",
    )
    assert patched.status_code == 200
    assert patched.json()["answer"] == "The beta-lactam ring"
    assert patched.json()["question"] == "Which ring is strained?"

    detail = integration_client.get(_detail(FLASHCARDS_URL, pk))
    assert detail.status_code == 200
    assert detail.json()["answer"] == "The beta-lactam ring"

    assert integration_client.delete(_detail(FLASHCARDS_URL, pk)).status_code == 204
    assert not Flashcard.objects.filter(pk=pk).exists()
    assert integration_client.delete(_detail(FLASHCARDS_URL, pk)).status_code == 404
    assert integration_client.get(_detail(FLASHCARDS_URL, 999999)).status_code == 404


@pytest.mark.django_db
def test_quiz_crud(integration_client, topic):
    created = integration_client.post(
        QUIZZES_URL,
        {"topic": topic.pk, "title": "Basics", "questions": [_question()]},
        format="json",
    )
    assert created.status_code == 201
    pk = created.json()["id"]

    listed = integration_client.get(QUIZZES_URL).json()
    assert [row["id"] for row in listed["results"]] == [pk]

    patched = integration_client.patch(
        _detail(QUIZZES_URL, pk),
        {"description": "Ten questions later"},
        format="json",
    )
    assert patched.status_code == 200
    assert patched.json()["description"] == "Ten questions later"
    assert len(patched.json()["questions"]) == 1

    assert integration_client.delete(_detail(QUIZZES_URL, pk)).status_code == 204
    assert not Quiz.objects.filter(pk=pk).exists()
    assert integration_client.delete(_detail(QUIZZES_URL, pk)).status_code == 404
    assert integration_client.get(_detail(QUIZZES_URL, 999999)).status_code == 404


@pytest.mark.django_db
def test_source_crud(integration_client, topic):
    created = integration_client.post(
        SOURCES_URL,
        {"title": "Guideline", "source_type": "guideline", "topic_ids": [topic.pk]},
        format="json",
    )
    assert created.status_code == 201
    pk = created.json()["id"]

    listed = integration_client.get(SOURCES_URL).json()
    assert [row["id"] for row in listed["results"]] == [pk]

    patched = integration_client.patch(
        _detail(SOURCES_URL, pk),
        {"author": "WHO"},
        format="json",
    )
    assert patched.status_code == 200
    assert patched.json()["author"] == "WHO"
    assert patched.json()["topic_ids"] == [topic.pk]

    detail = integration_client.get(_detail(SOURCES_URL, pk))
    assert detail.status_code == 200
    assert detail.json()["topic_ids"] == [topic.pk]

    assert integration_client.delete(_detail(SOURCES_URL, pk)).status_code == 204
    assert not Source.objects.filter(pk=pk).exists()
    assert integration_client.delete(_detail(SOURCES_URL, pk)).status_code == 404
    assert integration_client.get(_detail(SOURCES_URL, 999999)).status_code == 404


# ---------------------------------------------------------------------------
# 3. Strict payloads: unknown fields, unknown relations, invalid choices.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_unknown_top_level_field_names_the_offending_key(integration_client):
    response = integration_client.post(
        SUBJECTS_URL,
        {"title": "Anatomy", "slug": "anatomy"},
        format="json",
    )

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert "slug" in body["fields"]
    assert not Subject.objects.exists()


@pytest.mark.django_db
def test_unknown_relation_id_is_an_invalid_relation(integration_client, catalog):
    response = integration_client.post(
        SECTIONS_URL,
        {"subject": 999999, "title": "Antibiotics"},
        format="json",
    )

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "INVALID_RELATION"
    assert "subject" in body["fields"]
    assert Section.objects.count() == 1


@pytest.mark.django_db
def test_invalid_choice_values_are_validation_errors(
    integration_client, catalog, topic
):
    bad_status = integration_client.post(
        TOPICS_URL,
        {"section": catalog["section"].pk, "title": "Archived", "status": "archived"},
        format="json",
    )
    assert bad_status.status_code == 422
    assert bad_status.json()["code"] == "VALIDATION_ERROR"

    bad_access = integration_client.patch(
        _detail(TOPICS_URL, topic.pk),
        {"access_level": "premium"},
        format="json",
    )
    assert bad_access.status_code == 422
    assert bad_access.json()["code"] == "VALIDATION_ERROR"

    bad_source_type = integration_client.post(
        SOURCES_URL,
        {"title": "Podcast", "source_type": "podcast"},
        format="json",
    )
    assert bad_source_type.status_code == 422
    assert bad_source_type.json()["code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# 4. external_id: create, POST upsert, established identity is immutable.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_post_upserts_a_known_external_id_and_creates_a_new_one(integration_client):
    first = integration_client.post(
        SUBJECTS_URL,
        {"title": "Anatomy", "external_id": "anat-1"},
        format="json",
    )
    assert first.status_code == 201

    second = integration_client.post(
        SUBJECTS_URL,
        {"title": "Anatomy revised", "external_id": "anat-1"},
        format="json",
    )
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert Subject.objects.filter(external_id="anat-1").count() == 1
    assert Subject.objects.get(pk=first.json()["id"]).title == "Anatomy revised"

    third = integration_client.post(
        SUBJECTS_URL,
        {"title": "Physiology", "external_id": "phys-1"},
        format="json",
    )
    assert third.status_code == 201
    assert Subject.objects.count() == 2


@pytest.mark.django_db
def test_an_established_external_id_cannot_be_changed_or_cleared(integration_client):
    pk = integration_client.post(
        SUBJECTS_URL,
        {"title": "Anatomy", "external_id": "anat-1"},
        format="json",
    ).json()["id"]

    changed = integration_client.patch(
        _detail(SUBJECTS_URL, pk),
        {"external_id": "anat-2"},
        format="json",
    )
    assert changed.status_code == 409
    assert changed.json()["code"] == "EXTERNAL_ID_CONFLICT"

    cleared = integration_client.patch(
        _detail(SUBJECTS_URL, pk),
        {"external_id": None},
        format="json",
    )
    assert cleared.status_code == 409
    assert cleared.json()["code"] == "EXTERNAL_ID_CONFLICT"
    assert Subject.objects.get(pk=pk).external_id == "anat-1"


# ---------------------------------------------------------------------------
# 5. Blocks: publish preconditions, media merge rule, raw HTML, storage key.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_published_markdown_and_image_blocks_are_created(
    integration_client, topic, media_file
):
    markdown = integration_client.post(
        BLOCKS_URL,
        {
            "topic": topic.pk,
            "block_type": "markdown",
            "markdown_body": "# Beta-lactams",
            "status": "published",
        },
        format="json",
    )
    assert markdown.status_code == 201
    assert markdown.json()["markdown_body"] == "# Beta-lactams"
    assert markdown.json()["published_at"] is not None

    image = integration_client.post(
        BLOCKS_URL,
        {
            "topic": topic.pk,
            "block_type": "image",
            "media": media_file.pk,
            "caption": "Structure",
            "status": "published",
        },
        format="json",
    )
    assert image.status_code == 201
    assert image.json()["media"] == media_file.pk
    assert image.json()["published_at"] is not None


@pytest.mark.django_db
def test_publishing_an_image_block_without_media_is_refused(integration_client, topic):
    response = integration_client.post(
        BLOCKS_URL,
        {"topic": topic.pk, "block_type": "image", "status": "published"},
        format="json",
    )

    assert response.status_code == 409
    assert response.json()["code"] == "INVALID_CONTENT_STATE"
    assert not ContentBlock.objects.exists()


@pytest.mark.django_db
def test_patch_media_null_is_rechecked_against_the_publish_precondition(
    integration_client, published_image_block
):
    media, block = published_image_block()

    refused = integration_client.patch(
        _detail(BLOCKS_URL, block.pk),
        {"media": None},
        format="json",
    )
    assert refused.status_code == 409
    assert refused.json()["code"] == "INVALID_CONTENT_STATE"
    assert ContentBlock.objects.get(pk=block.pk).media_id == media.pk

    unpublished = integration_client.patch(
        _detail(BLOCKS_URL, block.pk),
        {"status": "draft"},
        format="json",
    )
    assert unpublished.status_code == 200

    detached = integration_client.patch(
        _detail(BLOCKS_URL, block.pk),
        {"media": None},
        format="json",
    )
    assert detached.status_code == 200
    assert detached.json()["media"] is None
    assert ContentBlock.objects.get(pk=block.pk).media_id is None


@pytest.mark.django_db
def test_raw_html_markdown_body_is_rejected(integration_client, topic):
    response = integration_client.post(
        BLOCKS_URL,
        {
            "topic": topic.pk,
            "block_type": "markdown",
            "markdown_body": "<script>alert(1)</script>",
        },
        format="json",
    )

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert not ContentBlock.objects.exists()


@pytest.mark.django_db
def test_authoring_block_reads_never_expose_the_storage_key(
    integration_client, topic, media_file
):
    created = integration_client.post(
        BLOCKS_URL,
        {"topic": topic.pk, "block_type": "image", "media": media_file.pk},
        format="json",
    )
    assert created.status_code == 201
    assert "storage_key" not in created.json()

    detail = integration_client.get(_detail(BLOCKS_URL, created.json()["id"]))
    assert "storage_key" not in detail.json()

    listed = integration_client.get(BLOCKS_URL)
    assert media_file.storage_key not in listed.content.decode()


# ---------------------------------------------------------------------------
# 6. Quiz aggregate: nested create, identity-preserving patch, invariants.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_quiz_create_returns_the_scalar_quiz_and_its_detail_nests_the_aggregate(
    integration_client, topic
):
    created = integration_client.post(
        QUIZZES_URL,
        {"topic": topic.pk, "title": "Basics", "questions": [_question()]},
        format="json",
    )
    assert created.status_code == 201
    assert "questions" not in created.json()

    detail = integration_client.get(_detail(QUIZZES_URL, created.json()["id"]))
    assert detail.status_code == 200
    body = detail.json()

    assert len(body["questions"]) == 1
    question = body["questions"][0]
    assert question["text"] == "Which are beta-lactams?"
    assert [answer["is_correct"] for answer in question["answers"]] == [True, False]
    assert all(isinstance(answer["id"], int) for answer in question["answers"])


@pytest.mark.django_db
def test_quiz_patch_updates_nested_items_in_place_and_keeps_omitted_ones(
    integration_client, topic
):
    created = _create_quiz(
        integration_client,
        topic,
        [_question(), _question("Which are macrolides?")],
    )
    first, second = created["questions"]
    answer_ids = [answer["id"] for answer in first["answers"]]

    patched = integration_client.patch(
        _detail(QUIZZES_URL, created["id"]),
        {
            "questions": [
                {
                    "id": first["id"],
                    "text": "Which ring is strained?",
                    "answers": [
                        {"id": answer_ids[0], "text": "Penicillin G"},
                        {"id": answer_ids[1], "text": "Gentamicin"},
                    ],
                }
            ]
        },
        format="json",
    )
    assert patched.status_code == 200
    body = patched.json()
    assert [question["id"] for question in body["questions"]] == [
        first["id"],
        second["id"],
    ]
    assert body["questions"][0]["text"] == "Which ring is strained?"
    assert [answer["id"] for answer in body["questions"][0]["answers"]] == answer_ids
    assert body["questions"][0]["answers"][0]["text"] == "Penicillin G"
    assert body["questions"][1]["text"] == "Which are macrolides?"

    kept = integration_client.patch(
        _detail(QUIZZES_URL, created["id"]),
        {"title": "Basics II"},
        format="json",
    )
    assert kept.status_code == 200
    assert [question["id"] for question in kept.json()["questions"]] == [
        first["id"],
        second["id"],
    ]
    assert Quiz.objects.get(pk=created["id"]).title == "Basics II"


@pytest.mark.django_db
def test_a_nested_id_from_another_quiz_is_an_invalid_relation(
    integration_client, topic
):
    first = _create_quiz(integration_client, topic, [_question()], title="First")
    second = _create_quiz(integration_client, topic, [_question()], title="Second")
    foreign_question = first["questions"][0]

    response = integration_client.patch(
        _detail(QUIZZES_URL, second["id"]),
        {"questions": [{"id": foreign_question["id"], "text": "Hijacked?"}]},
        format="json",
    )

    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_RELATION"
    assert (
        QuizQuestion.objects.get(pk=foreign_question["id"]).text
        == "Which are beta-lactams?"
    )


@pytest.mark.django_db
def test_quiz_create_rejects_an_unsatisfiable_aggregate(integration_client, topic):
    one_answer = integration_client.post(
        QUIZZES_URL,
        {
            "topic": topic.pk,
            "title": "Basics",
            "questions": [
                {"text": "Q?", "answers": [{"text": "Only", "is_correct": True}]}
            ],
        },
        format="json",
    )
    assert one_answer.status_code == 422
    assert one_answer.json()["code"] == "VALIDATION_ERROR"

    no_correct_answer = integration_client.post(
        QUIZZES_URL,
        {
            "topic": topic.pk,
            "title": "Basics",
            "questions": [{"text": "Q?", "answers": [{"text": "A"}, {"text": "B"}]}],
        },
        format="json",
    )
    assert no_correct_answer.status_code == 422
    assert no_correct_answer.json()["code"] == "VALIDATION_ERROR"

    no_questions = integration_client.post(
        QUIZZES_URL,
        {"topic": topic.pk, "title": "Basics"},
        format="json",
    )
    assert no_questions.status_code == 422
    assert no_questions.json()["code"] == "VALIDATION_ERROR"
    assert not Quiz.objects.exists()


@pytest.mark.django_db
def test_quiz_patch_that_breaks_the_aggregate_is_a_conflict(integration_client, topic):
    created = _create_quiz(integration_client, topic, [_question()])
    question = created["questions"][0]

    response = integration_client.patch(
        _detail(QUIZZES_URL, created["id"]),
        {
            "questions": [
                {
                    "id": question["id"],
                    "text": question["text"],
                    "answers": [
                        {
                            "id": question["answers"][0]["id"],
                            "text": "Penicillin",
                            "is_correct": False,
                        }
                    ],
                }
            ]
        },
        format="json",
    )

    assert response.status_code == 409
    assert response.json()["code"] == "CONTENT_CONFLICT"
    assert QuizAnswer.objects.filter(
        question_id=question["id"], is_correct=True
    ).exists()


@pytest.mark.django_db
def test_quiz_list_returns_scalar_fields_only(integration_client, topic):
    integration_client.post(
        QUIZZES_URL,
        {"topic": topic.pk, "title": "Basics", "questions": [_question()]},
        format="json",
    )

    listed = integration_client.get(QUIZZES_URL).json()

    assert set(listed["results"][0]) == {
        "id",
        "topic",
        "title",
        "description",
        "position",
        "external_id",
    }


# ---------------------------------------------------------------------------
# 7. Explicit deletion: the Topic aggregate and its sibling boundary.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_topic_delete_removes_its_aggregate_and_keeps_siblings(
    integration_client, catalog, topic
):
    sibling = catalog["add_topic"](title="Macrolides", slug="macrolides", position=2)
    block = integration_client.post(
        BLOCKS_URL,
        {"topic": topic.pk, "block_type": "markdown", "markdown_body": "# Body"},
        format="json",
    ).json()
    flashcard = integration_client.post(
        FLASHCARDS_URL,
        {"topic": topic.pk, "question": "Q?", "answer": "A."},
        format="json",
    ).json()
    quiz = _create_quiz(integration_client, topic, [_question()])
    answer_ids = [answer["id"] for answer in quiz["questions"][0]["answers"]]

    response = integration_client.delete(_detail(TOPICS_URL, topic.pk))

    assert response.status_code == 204
    assert not Topic.objects.filter(pk=topic.pk).exists()
    assert not ContentBlock.objects.filter(pk=block["id"]).exists()
    assert not Flashcard.objects.filter(pk=flashcard["id"]).exists()
    assert not Quiz.objects.filter(pk=quiz["id"]).exists()
    assert not QuizQuestion.objects.filter(quiz_id=quiz["id"]).exists()
    assert not QuizAnswer.objects.filter(pk__in=answer_ids).exists()

    assert Topic.objects.filter(pk=sibling.pk).exists()
    assert Section.objects.filter(pk=catalog["section"].pk).exists()
    assert Subject.objects.filter(pk=catalog["subject"].pk).exists()

    repeated = integration_client.delete(_detail(TOPICS_URL, topic.pk))
    assert repeated.status_code == 404
    assert repeated.json()["code"] == "RESOURCE_NOT_FOUND"


@pytest.mark.django_db
def test_deleting_a_subject_that_still_owns_sections_is_a_conflict(
    integration_client, catalog
):
    subject = catalog["subject"]

    response = integration_client.delete(_detail(SUBJECTS_URL, subject.pk))

    assert response.status_code == 409
    assert response.json()["code"] == "CONTENT_CONFLICT"
    assert Subject.objects.filter(pk=subject.pk).exists()


# ---------------------------------------------------------------------------
# 8. Sources: relation id sets and delete-removes-links-only.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_source_id_lists_set_the_relations_and_null_or_absent_keeps_them(
    integration_client, topic
):
    block = integration_client.post(
        BLOCKS_URL,
        {"topic": topic.pk, "block_type": "markdown", "markdown_body": "# Body"},
        format="json",
    ).json()
    flashcard = integration_client.post(
        FLASHCARDS_URL,
        {"topic": topic.pk, "question": "Q?", "answer": "A."},
        format="json",
    ).json()
    quiz = _create_quiz(integration_client, topic, [_question()])
    question_id = quiz["questions"][0]["id"]

    created = integration_client.post(
        SOURCES_URL,
        {
            "title": "Guideline",
            "source_type": "guideline",
            "topic_ids": [topic.pk],
            "block_ids": [block["id"]],
            "flashcard_ids": [flashcard["id"]],
            "question_ids": [question_id],
        },
        format="json",
    )
    assert created.status_code == 201
    body = created.json()
    assert body["topic_ids"] == [topic.pk]
    assert body["block_ids"] == [block["id"]]
    assert body["flashcard_ids"] == [flashcard["id"]]
    assert body["question_ids"] == [question_id]

    omitted = integration_client.patch(
        _detail(SOURCES_URL, body["id"]),
        {"title": "Guideline II"},
        format="json",
    )
    assert omitted.status_code == 200
    assert omitted.json()["topic_ids"] == [topic.pk]
    assert omitted.json()["block_ids"] == [block["id"]]

    nulled = integration_client.patch(
        _detail(SOURCES_URL, body["id"]),
        {"block_ids": None, "flashcard_ids": None},
        format="json",
    )
    assert nulled.status_code == 200
    assert nulled.json()["block_ids"] == [block["id"]]
    assert nulled.json()["flashcard_ids"] == [flashcard["id"]]

    cleared = integration_client.patch(
        _detail(SOURCES_URL, body["id"]),
        {"flashcard_ids": []},
        format="json",
    )
    assert cleared.status_code == 200
    assert cleared.json()["flashcard_ids"] == []
    assert Flashcard.objects.filter(pk=flashcard["id"]).exists()


@pytest.mark.django_db
def test_deleting_a_source_removes_links_only(integration_client, topic):
    flashcard = integration_client.post(
        FLASHCARDS_URL,
        {"topic": topic.pk, "question": "Q?", "answer": "A."},
        format="json",
    ).json()
    source = integration_client.post(
        SOURCES_URL,
        {
            "title": "Article",
            "source_type": "article",
            "flashcard_ids": [flashcard["id"]],
        },
        format="json",
    ).json()

    response = integration_client.delete(_detail(SOURCES_URL, source["id"]))

    assert response.status_code == 204
    assert not Source.objects.filter(pk=source["id"]).exists()
    stored = Flashcard.objects.get(pk=flashcard["id"])
    assert stored.sources.count() == 0


# ---------------------------------------------------------------------------
# 9. OpenAPI coverage and integration throttling.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_openapi_contains_the_fourteen_content_paths():
    schema = SchemaGenerator().get_schema(request=None, public=True)
    paths = schema["paths"]

    assert len(CONTENT_PATHS) == 14
    assert [path for path in CONTENT_PATHS if path not in paths] == []
    assert set(paths["/api/v1/content/subjects/"]) == {"get", "post"}
    assert set(paths["/api/v1/content/subjects/{id}/"]) == {"get", "patch", "delete"}
    assert set(paths["/api/v1/content/quizzes/{id}/"]) == {"get", "patch", "delete"}


@pytest.mark.django_db
def test_integration_writes_are_throttled(integration_client, monkeypatch):
    monkeypatch.setattr(
        ScopedRateThrottle,
        "THROTTLE_RATES",
        {"integration_write": "2/min"},
    )

    for index in range(2):
        allowed = integration_client.post(
            SUBJECTS_URL,
            {"title": f"Subject {index}"},
            format="json",
        )
        assert allowed.status_code == 201

    throttled = integration_client.post(
        SUBJECTS_URL,
        {"title": "Subject 3"},
        format="json",
    )

    assert throttled.status_code == 429
    assert throttled.json()["code"] == "THROTTLED"


# ---------------------------------------------------------------------------
# 10. Pagination.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_collection_page_size_is_respected_and_capped(integration_client):
    Subject.objects.bulk_create(
        Subject(title=f"Subject {index}", slug=f"subject-{index}", position=index)
        for index in range(101)
    )

    first_page = integration_client.get(f"{SUBJECTS_URL}?page_size=2").json()
    assert first_page["count"] == 101
    assert len(first_page["results"]) == 2

    capped = integration_client.get(f"{SUBJECTS_URL}?page_size=500").json()
    assert len(capped["results"]) == 100
