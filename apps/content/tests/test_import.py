from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from apps.content.admin import TopicImportForm
from apps.content.import_services import ContentImportError, import_study_document
from apps.content.models import (
    ContentBlock,
    ContentBlockType,
    Flashcard,
    Quiz,
    QuizAnswer,
    QuizQuestion,
    Section,
    Subject,
    Topic,
)


def _make_valid_payload(
    *,
    topic_title: str = "Стафилококки",
    schema_version: int = 1,
) -> dict:
    return {
        "schema_version": schema_version,
        "topic": topic_title,
        "content": {
            "title": topic_title,
            "summary": "Краткое описание стафилококков",
            "exam_focus": ["Факторы патогенности", "Лечение MRSA"],
            "blocks": [
                {
                    "block_type": "markdown",
                    "caption": "Общая характеристика",
                    "markdown_body": (
                        "## Общая характеристика\n\nТекст о стафилококках."
                    ),
                },
                {
                    "block_type": "callout",
                    "caption": "На экзамене",
                    "markdown_body": (
                        "## На экзамене\n\nОбратите внимание на коагулазу."
                    ),
                },
            ],
        },
        "flashcards": [
            {
                "question": (
                    "Какой фермент отличает S. aureus от эпидермального стафилококка?"
                ),
                "answer": "Плазмокоагулаза.",
            },
        ],
        "quiz": {
            "title": topic_title,
            "description": "Тест по стафилококкам",
            "questions": [
                {
                    "text": "Какая окраска по Граму характерна для стафилококков?",
                    "answers": [
                        {"text": "Грамположительные кокки", "is_correct": True},
                        {"text": "Грамотрицательные палочки", "is_correct": False},
                    ],
                },
            ],
        },
        "generation": {
            "provider": "openai",
            "model": "gpt-4o",
            "generated_at": "2026-09-23T12:00:00Z",
        },
    }


@pytest.fixture
def subject_and_section(db):
    subject = Subject.objects.create(
        title="Микробиология",
        slug="mikrobiologiya",
        position=1,
    )
    section = Section.objects.create(
        subject=subject,
        title="Бактериология",
        slug="bakteriologiya",
        position=1,
    )
    return subject, section


@pytest.mark.django_db
def test_valid_json_import_creates_all_entities(subject_and_section):
    subject, section = subject_and_section
    payload = _make_valid_payload()

    result = import_study_document(
        payload,
        section=section,
        status=Topic.Status.PUBLISHED,
        access_level=Topic.AccessLevel.FREE,
    )

    assert result.created is True
    assert result.blocks_count == 2
    assert result.flashcards_count == 1
    assert result.questions_count == 1
    assert result.answers_count == 2

    # Verify Topic
    topic = Topic.objects.get(pk=result.topic.pk)
    assert topic.title == "Стафилококки"
    assert topic.section == section
    assert topic.status == Topic.Status.PUBLISHED
    assert topic.access_level == Topic.AccessLevel.FREE
    assert topic.external_id == "medcore-content:topic:stafilokokki"

    # Verify Blocks
    blocks = list(topic.blocks.order_by("position"))
    assert len(blocks) == 2
    assert blocks[0].position == 1
    assert blocks[0].block_type.key == "markdown"
    assert blocks[0].caption == "Общая характеристика"
    assert "Текст о стафилококках" in blocks[0].markdown_body
    assert blocks[0].status == ContentBlock.Status.PUBLISHED

    assert blocks[1].position == 2
    assert blocks[1].block_type.key == "callout"
    assert blocks[1].caption == "На экзамене"
    assert blocks[1].status == ContentBlock.Status.PUBLISHED

    # Verify Flashcards
    flashcards = list(topic.flashcards.order_by("position"))
    assert len(flashcards) == 1
    assert flashcards[0].position == 1
    assert (
        flashcards[0].question
        == "Какой фермент отличает S. aureus от эпидермального стафилококка?"
    )
    assert flashcards[0].answer == "Плазмокоагулаза."

    # Verify Quiz
    quizzes = list(topic.quizzes.all())
    assert len(quizzes) == 1
    quiz = quizzes[0]
    assert quiz.title == "Стафилококки"
    assert quiz.description == "Тест по стафилококкам"
    assert quiz.external_id == "medcore-content:topic:stafilokokki:quiz"

    questions = list(quiz.questions.order_by("position"))
    assert len(questions) == 1
    assert questions[0].position == 1
    assert questions[0].text == "Какая окраска по Граму характерна для стафилококков?"

    answers = list(questions[0].answers.order_by("position"))
    assert len(answers) == 2
    assert answers[0].position == 1
    assert answers[0].text == "Грамположительные кокки"
    assert answers[0].is_correct is True
    assert answers[1].position == 2
    assert answers[1].text == "Грамотрицательные палочки"
    assert answers[1].is_correct is False


@pytest.mark.django_db
def test_import_preserves_order_of_all_nested_entities(subject_and_section):
    subject, section = subject_and_section
    payload = _make_valid_payload()
    payload["content"]["blocks"].append(
        {
            "block_type": "markdown",
            "caption": "Третий блок",
            "markdown_body": "Содержимое третьего блока",
        }
    )
    payload["flashcards"].append(
        {
            "question": "Вторая карточка?",
            "answer": "Второй ответ.",
        }
    )
    payload["quiz"]["questions"].append(
        {
            "text": "Второй вопрос?",
            "answers": [
                {"text": "Ответ 1", "is_correct": False},
                {"text": "Ответ 2", "is_correct": True},
                {"text": "Ответ 3", "is_correct": False},
            ],
        }
    )

    result = import_study_document(payload, section=section)
    topic = result.topic

    # Order check
    assert list(
        topic.blocks.order_by("position").values_list("position", flat=True)
    ) == [1, 2, 3]
    assert list(
        topic.flashcards.order_by("position").values_list("position", flat=True)
    ) == [1, 2]
    quiz = topic.quizzes.first()
    assert list(
        quiz.questions.order_by("position").values_list("position", flat=True)
    ) == [1, 2]
    q2 = quiz.questions.get(position=2)
    assert list(q2.answers.order_by("position").values_list("position", flat=True)) == [
        1,
        2,
        3,
    ]


@pytest.mark.django_db
def test_repeated_import_idempotent_and_updates_content(subject_and_section):
    subject, section = subject_and_section
    payload = _make_valid_payload()

    # First import
    res1 = import_study_document(payload, section=section)
    assert res1.created is True
    assert Topic.objects.count() == 1
    assert ContentBlock.objects.count() == 2
    assert Flashcard.objects.count() == 1
    assert Quiz.objects.count() == 1
    assert QuizQuestion.objects.count() == 1
    assert QuizAnswer.objects.count() == 2

    # Modify payload for second import
    payload["content"]["blocks"][0]["markdown_body"] = "Обновленный текст"
    # Remove second block (now 1 block)
    payload["content"]["blocks"] = payload["content"]["blocks"][:1]
    # Update flashcard
    payload["flashcards"][0]["answer"] = "Обновленный ответ"
    # Update quiz question and answer
    payload["quiz"]["questions"][0]["text"] = "Обновленный вопрос?"
    payload["quiz"]["questions"][0]["answers"][0]["text"] = (
        "Обновленный правильный ответ"
    )

    # Second import
    res2 = import_study_document(payload, section=section)
    assert res2.created is False
    assert res2.topic.pk == res1.topic.pk

    # Topic count unchanged
    assert Topic.objects.count() == 1
    # Blocks reduced to 1 and content updated
    assert ContentBlock.objects.filter(topic=res2.topic).count() == 1
    b = ContentBlock.objects.get(topic=res2.topic)
    assert b.markdown_body == "Обновленный текст"

    # Flashcard updated
    assert Flashcard.objects.filter(topic=res2.topic).count() == 1
    fc = Flashcard.objects.get(topic=res2.topic)
    assert fc.answer == "Обновленный ответ"

    # Quiz question updated
    q = QuizQuestion.objects.get(quiz__topic=res2.topic)
    assert q.text == "Обновленный вопрос?"
    a1 = q.answers.get(is_correct=True)
    assert a1.text == "Обновленный правильный ответ"


@pytest.mark.django_db
def test_invalid_json_creates_nothing(subject_and_section):
    subject, section = subject_and_section
    invalid_payload = {"schema_version": 1, "topic": ""}

    with pytest.raises(ContentImportError):
        import_study_document(invalid_payload, section=section)

    assert Topic.objects.count() == 0
    assert ContentBlock.objects.count() == 0


@pytest.mark.django_db
def test_unsupported_schema_version_rejected(subject_and_section):
    subject, section = subject_and_section
    payload = _make_valid_payload(schema_version=2)

    with pytest.raises(ContentImportError) as exc_info:
        import_study_document(payload, section=section)

    assert "schema_version 2 is not supported" in str(exc_info.value)
    assert Topic.objects.count() == 0


@pytest.mark.django_db
def test_unknown_block_type_rejected(subject_and_section):
    subject, section = subject_and_section
    payload = _make_valid_payload()
    payload["content"]["blocks"][0]["block_type"] = "foo_bar"

    with pytest.raises(ContentImportError) as exc_info:
        import_study_document(payload, section=section)

    assert "Unknown block_type" in str(exc_info.value)
    assert Topic.objects.count() == 0


@pytest.mark.django_db
def test_missing_content_block_type_in_db_rejected(subject_and_section):
    subject, section = subject_and_section
    ContentBlockType.objects.filter(key="callout").update(active=False)

    payload = _make_valid_payload()

    with pytest.raises(ContentImportError) as exc_info:
        import_study_document(payload, section=section)

    assert 'ContentBlockType "callout" does not exist' in str(exc_info.value)
    assert Topic.objects.count() == 0


@pytest.mark.django_db
def test_quiz_zero_correct_answers_rejected(subject_and_section):
    subject, section = subject_and_section
    payload = _make_valid_payload()
    for ans in payload["quiz"]["questions"][0]["answers"]:
        ans["is_correct"] = False

    with pytest.raises(ContentImportError) as exc_info:
        import_study_document(payload, section=section)

    assert "exactly one correct answer" in str(exc_info.value)
    assert Topic.objects.count() == 0


@pytest.mark.django_db
def test_quiz_multiple_correct_answers_rejected(subject_and_section):
    subject, section = subject_and_section
    payload = _make_valid_payload()
    for ans in payload["quiz"]["questions"][0]["answers"]:
        ans["is_correct"] = True

    with pytest.raises(ContentImportError) as exc_info:
        import_study_document(payload, section=section)

    assert "exactly one correct answer" in str(exc_info.value)
    assert Topic.objects.count() == 0


@pytest.mark.django_db
def test_quiz_duplicate_answer_text_rejected(subject_and_section):
    subject, section = subject_and_section
    payload = _make_valid_payload()
    payload["quiz"]["questions"][0]["answers"] = [
        {"text": "Одинаковый ответ", "is_correct": True},
        {"text": "  одинаковый ответ  ", "is_correct": False},
    ]

    with pytest.raises(ContentImportError) as exc_info:
        import_study_document(payload, section=section)

    assert "Duplicate answer text" in str(exc_info.value)
    assert Topic.objects.count() == 0


@pytest.mark.django_db
def test_quiz_less_than_two_answers_rejected(subject_and_section):
    subject, section = subject_and_section
    payload = _make_valid_payload()
    payload["quiz"]["questions"][0]["answers"] = [
        {"text": "Единственный ответ", "is_correct": True},
    ]

    with pytest.raises(ContentImportError) as exc_info:
        import_study_document(payload, section=section)

    assert "must contain at least 2 answers" in str(exc_info.value)
    assert Topic.objects.count() == 0


@pytest.mark.django_db
def test_quiz_empty_questions_rejected(subject_and_section):
    subject, section = subject_and_section
    payload = _make_valid_payload()
    payload["quiz"]["questions"] = []

    with pytest.raises(ContentImportError) as exc_info:
        import_study_document(payload, section=section)

    assert "must contain at least 1 question" in str(exc_info.value)
    assert Topic.objects.count() == 0


@pytest.mark.django_db
def test_section_from_wrong_subject_form_validation(subject_and_section):
    subject1, section1 = subject_and_section
    subject2 = Subject.objects.create(
        title="Фармакология", slug="farmakologiya", position=2
    )

    # section1 belongs to subject1, but subject2 is selected in form
    file_content = json.dumps(_make_valid_payload()).encode("utf-8")
    uploaded_file = SimpleUploadedFile(
        "doc.json", file_content, content_type="application/json"
    )

    form = TopicImportForm(
        data={
            "subject": subject2.pk,
            "section": section1.pk,
            "status": Topic.Status.DRAFT,
            "access_level": Topic.AccessLevel.DEMO,
        },
        files={"file": uploaded_file},
    )

    assert not form.is_valid()
    assert "section" in form.errors
    assert (
        "Selected section does not belong to selected subject"
        in form.errors["section"][0]
    )


@pytest.mark.django_db
def test_transaction_rollback_on_failure_midway(subject_and_section):
    subject, section = subject_and_section
    payload = _make_valid_payload()

    # Force failure during flashcard creation
    with patch(
        "apps.content.services.upsert_flashcard",
        side_effect=RuntimeError("Simulated DB failure"),
    ):
        with pytest.raises(RuntimeError):
            import_study_document(payload, section=section)

    # Verify atomic rollback: topic and blocks must not remain
    assert Topic.objects.count() == 0
    assert ContentBlock.objects.count() == 0
    assert Flashcard.objects.count() == 0
    assert Quiz.objects.count() == 0


@pytest.mark.django_db
def test_admin_import_page_permissions(make_user, subject_and_section):
    client = Client()
    import_url = "/admin/content/topic/import-json/"

    # 1. Anonymous user
    resp_anon = client.get(import_url)
    assert resp_anon.status_code == 302
    assert "/admin/login/" in resp_anon.url

    # 2. Plain user (non-staff)
    plain_user = make_user(username="regular", role="user", is_staff=False)
    client.force_login(plain_user)
    resp_user = client.get(import_url)
    assert resp_user.status_code == 302
    assert "/admin/login/" in resp_user.url

    # 3. Staff user without editor/admin role
    staff_user = make_user(username="staff_only", role="user", is_staff=True)
    client.force_login(staff_user)
    resp_staff = client.get(import_url)
    assert resp_staff.status_code == 403

    # 4. Editor staff user
    editor_user = make_user(username="content_editor", role="editor", is_staff=True)
    client.force_login(editor_user)
    resp_editor = client.get(import_url)
    assert resp_editor.status_code == 200
    assert "Import Medcore JSON" in resp_editor.content.decode("utf-8")

    # 5. Superuser
    admin_user = make_user(
        username="super_admin", role="admin", is_staff=True, is_superuser=True
    )
    client.force_login(admin_user)
    resp_admin = client.get(import_url)
    assert resp_admin.status_code == 200


@pytest.mark.django_db
def test_admin_import_flow_post_success(make_user, subject_and_section):
    subject, section = subject_and_section
    editor = make_user(username="editor_flow", role="editor", is_staff=True)
    client = Client()
    client.force_login(editor)

    payload = _make_valid_payload()
    json_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    uploaded = SimpleUploadedFile(
        "staphylococcus.json", json_bytes, content_type="application/json"
    )

    resp = client.post(
        "/admin/content/topic/import-json/",
        data={
            "subject": subject.pk,
            "section": section.pk,
            "status": Topic.Status.PUBLISHED,
            "access_level": Topic.AccessLevel.FREE,
            "file": uploaded,
        },
    )

    assert resp.status_code == 302
    topic = Topic.objects.get(external_id="medcore-content:topic:stafilokokki")
    assert resp.url == f"/admin/content/topic/{topic.pk}/change/"


@pytest.mark.django_db
def test_admin_import_file_too_large(make_user, subject_and_section):
    subject, section = subject_and_section
    editor = make_user(username="editor_size", role="editor", is_staff=True)
    client = Client()
    client.force_login(editor)

    # 6 MB dummy content
    large_bytes = b"{" + b" " * (6 * 1024 * 1024) + b"}"
    uploaded = SimpleUploadedFile(
        "huge.json", large_bytes, content_type="application/json"
    )

    resp = client.post(
        "/admin/content/topic/import-json/",
        data={
            "subject": subject.pk,
            "section": section.pk,
            "status": Topic.Status.DRAFT,
            "access_level": Topic.AccessLevel.DEMO,
            "file": uploaded,
        },
    )

    assert resp.status_code == 200
    assert "File is too large" in resp.content.decode("utf-8")


@pytest.mark.django_db
def test_admin_import_non_json_extension(make_user, subject_and_section):
    subject, section = subject_and_section
    editor = make_user(username="editor_ext", role="editor", is_staff=True)
    client = Client()
    client.force_login(editor)

    uploaded = SimpleUploadedFile("data.txt", b"some text", content_type="text/plain")

    resp = client.post(
        "/admin/content/topic/import-json/",
        data={
            "subject": subject.pk,
            "section": section.pk,
            "status": Topic.Status.DRAFT,
            "access_level": Topic.AccessLevel.DEMO,
            "file": uploaded,
        },
    )

    assert resp.status_code == 200
    assert "Only .json files are supported" in resp.content.decode("utf-8")
