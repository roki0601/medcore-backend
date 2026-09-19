"""Service-level tests for the 004 content write layer."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

import pytest
from django.db import connections
from django.test import TransactionTestCase

from apps.common.exceptions import APIError
from apps.content import services
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


def _question(text: str = "Which are beta-lactams?", *, correct: str = "Penicillin"):
    return {
        "text": text,
        "answers": [
            {"text": correct, "is_correct": True},
            {"text": "Gentamicin"},
        ],
    }


@pytest.fixture
def topic(catalog) -> Topic:
    return catalog["add_topic"](title="Beta-lactams", slug="beta-lactams", position=1)


@pytest.fixture
def other_topic(catalog) -> Topic:
    return catalog["add_topic"](title="Macrolides", slug="macrolides", position=2)


# ---------------------------------------------------------------------------
# external_id identity: create, POST upsert, immutability.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_upsert_subject_creates_then_upserts_by_external_id():
    subject, created = services.upsert_subject(
        title="Pharmacology",
        external_id="subj-1",
        external_id_provided=True,
    )
    assert created is True
    assert subject.external_id == "subj-1"

    updated, created_again = services.upsert_subject(
        title="Pharmacology II",
        description="Revised",
        external_id="subj-1",
        external_id_provided=True,
    )
    assert created_again is False
    assert updated.pk == subject.pk
    assert updated.title == "Pharmacology II"
    assert updated.description == "Revised"
    assert updated.position == subject.position
    assert Subject.objects.filter(external_id="subj-1").count() == 1


@pytest.mark.django_db
def test_upsert_functions_create_then_upsert_section_topic_block_and_flashcard(catalog):
    subject = catalog["subject"]

    section, created = services.upsert_section(
        subject,
        title="Antibiotics",
        external_id="sec-1",
        external_id_provided=True,
    )
    assert created is True
    section_again, created_again = services.upsert_section(
        subject,
        title="Antibiotics II",
        external_id="sec-1",
        external_id_provided=True,
    )
    assert created_again is False
    assert section_again.pk == section.pk
    assert section_again.title == "Antibiotics II"
    assert section_again.position == section.position
    assert Section.objects.filter(external_id="sec-1").count() == 1

    topic, created = services.upsert_topic(
        section,
        title="Beta-lactams",
        status=Topic.Status.PUBLISHED,
        access_level=Topic.AccessLevel.FREE,
        external_id="top-1",
        external_id_provided=True,
    )
    assert created is True
    topic_again, created_again = services.upsert_topic(
        section,
        title="Beta-lactams II",
        status=Topic.Status.PUBLISHED,
        access_level=Topic.AccessLevel.FREE,
        external_id="top-1",
        external_id_provided=True,
    )
    assert created_again is False
    assert topic_again.pk == topic.pk
    assert topic_again.position == topic.position
    assert Topic.objects.filter(external_id="top-1").count() == 1

    block, created = services.upsert_content_block(
        topic,
        block_type_key="markdown",
        markdown_body="# Theory",
        external_id="blk-1",
        external_id_provided=True,
    )
    assert created is True
    block_again, created_again = services.upsert_content_block(
        topic,
        block_type_key="markdown",
        markdown_body="# Theory revised",
        external_id="blk-1",
        external_id_provided=True,
    )
    assert created_again is False
    assert block_again.pk == block.pk
    assert block_again.markdown_body == "# Theory revised"
    assert block_again.position == block.position
    assert ContentBlock.objects.filter(external_id="blk-1").count() == 1

    flashcard, created = services.upsert_flashcard(
        topic,
        question="Which ring is strained?",
        answer="The beta-lactam ring",
        external_id="card-1",
        external_id_provided=True,
    )
    assert created is True
    flashcard_again, created_again = services.upsert_flashcard(
        topic,
        question="Which ring is strained?",
        answer="The four-membered beta-lactam ring",
        external_id="card-1",
        external_id_provided=True,
    )
    assert created_again is False
    assert flashcard_again.pk == flashcard.pk
    assert flashcard_again.answer == "The four-membered beta-lactam ring"
    assert flashcard_again.position == flashcard.position
    assert Flashcard.objects.filter(external_id="card-1").count() == 1


@pytest.mark.django_db
def test_upsert_source_creates_then_upserts_by_external_id():
    source, created = services.upsert_source(
        title="Guideline",
        source_type=Source.SourceType.GUIDELINE,
        external_id="src-1",
        external_id_provided=True,
    )
    assert created is True

    updated, created_again = services.upsert_source(
        title="Guideline 2024",
        source_type=Source.SourceType.GUIDELINE,
        year=2024,
        external_id="src-1",
        external_id_provided=True,
    )
    assert created_again is False
    assert updated.pk == source.pk
    assert updated.year == 2024
    assert Source.objects.filter(external_id="src-1").count() == 1


@pytest.mark.django_db
def test_established_external_id_cannot_be_changed_or_cleared():
    subject, _ = services.upsert_subject(
        title="Pharmacology",
        external_id="subj-1",
        external_id_provided=True,
    )

    with pytest.raises(APIError) as changed:
        services.upsert_subject(
            title="Pharmacology",
            external_id="subj-2",
            external_id_provided=True,
            instance=subject,
        )
    assert changed.value.default_code == "EXTERNAL_ID_CONFLICT"
    assert changed.value.status_code == 409

    with pytest.raises(APIError) as cleared:
        services.upsert_subject(
            title="Pharmacology",
            external_id=None,
            external_id_provided=True,
            instance=subject,
        )
    assert cleared.value.default_code == "EXTERNAL_ID_CONFLICT"

    with pytest.raises(APIError) as cleared_with_blank:
        services.upsert_subject(
            title="Pharmacology",
            external_id="",
            external_id_provided=True,
            instance=subject,
        )
    assert cleared_with_blank.value.default_code == "EXTERNAL_ID_CONFLICT"

    assert Subject.objects.get(pk=subject.pk).external_id == "subj-1"


@pytest.mark.django_db
def test_assigning_a_taken_external_id_is_a_conflict_but_a_post_upserts():
    owner, _ = services.upsert_subject(
        title="Pharmacology",
        external_id="subj-1",
        external_id_provided=True,
    )
    other = services.save_subject(title="Anatomy")

    with pytest.raises(APIError) as taken:
        services.upsert_subject(
            title="Anatomy",
            external_id="subj-1",
            external_id_provided=True,
            instance=other,
        )
    assert taken.value.default_code == "EXTERNAL_ID_CONFLICT"
    assert taken.value.status_code == 409

    upserted, created = services.upsert_subject(
        title="Anatomy",
        external_id="subj-1",
        external_id_provided=True,
    )
    assert created is False
    assert upserted.pk == owner.pk
    assert Subject.objects.filter(external_id="subj-1").count() == 1


@pytest.mark.django_db
def test_external_id_is_absent_versus_explicitly_cleared():
    subject, created = services.upsert_subject(
        title="Pharmacology",
        external_id="",
        external_id_provided=True,
    )
    assert created is True
    assert subject.external_id is None

    cleared, created_again = services.upsert_subject(
        title="Pharmacology",
        external_id="",
        external_id_provided=True,
        instance=subject,
    )
    assert created_again is False
    assert cleared.external_id is None

    named, _ = services.upsert_subject(
        title="Pharmacology",
        external_id="subj-1",
        external_id_provided=True,
        instance=subject,
    )
    assert named.external_id == "subj-1"

    untouched, created_again = services.upsert_subject(
        title="Pharmacology II",
        instance=named,
    )
    assert created_again is False
    assert untouched.external_id == "subj-1"


@pytest.mark.django_db
def test_blank_and_oversized_external_id_are_validation_errors():
    with pytest.raises(APIError) as blank:
        services.upsert_subject(
            title="Pharmacology",
            external_id="   ",
            external_id_provided=True,
        )
    assert blank.value.default_code == "VALIDATION_ERROR"
    assert blank.value.status_code == 422
    assert "external_id" in blank.value.fields

    with pytest.raises(APIError) as oversized:
        services.upsert_subject(
            title="Pharmacology",
            external_id="x" * (services.EXTERNAL_ID_MAX_LENGTH + 1),
            external_id_provided=True,
        )
    assert oversized.value.default_code == "VALIDATION_ERROR"
    assert oversized.value.status_code == 422
    assert not Subject.objects.exists()


# ---------------------------------------------------------------------------
# Quiz aggregate.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_quiz_aggregate_create_and_update_preserve_child_ids(topic):
    quiz, created = services.upsert_quiz(
        topic,
        title="Basics",
        external_id="quiz-1",
        external_id_provided=True,
        questions=[_question()],
    )
    assert created is True
    question = quiz.questions.get()
    answers = list(question.answers.order_by("position", "id"))
    assert [answer.is_correct for answer in answers] == [True, False]
    assert [answer.position for answer in answers] == [1, 2]

    updated, created_again = services.upsert_quiz(
        topic,
        title="Basics II",
        external_id="quiz-1",
        external_id_provided=True,
        questions=[
            {
                "id": question.pk,
                "text": "Which are beta-lactams?",
                "answers": [
                    {"id": answers[0].pk, "text": "Penicillin G", "is_correct": True},
                    {"id": answers[1].pk, "text": "Gentamicin"},
                ],
            },
            _question("Which are macrolides?", correct="Erythromycin"),
        ],
    )
    assert created_again is False
    assert updated.pk == quiz.pk
    assert updated.title == "Basics II"
    assert updated.position == quiz.position
    assert Quiz.objects.filter(external_id="quiz-1").count() == 1

    first = updated.questions.get(pk=question.pk)
    assert first.text == "Which are beta-lactams?"
    first_answers = list(first.answers.order_by("position", "id"))
    assert [answer.pk for answer in first_answers] == [answers[0].pk, answers[1].pk]
    assert first_answers[0].text == "Penicillin G"

    new_question = updated.questions.exclude(pk=question.pk).get()
    assert new_question.position == 2
    assert new_question.answers.count() == 2


@pytest.mark.django_db
def test_omitted_quiz_children_are_never_deleted(topic):
    quiz, _ = services.upsert_quiz(
        topic,
        title="Basics",
        questions=[_question(), _question("Which are macrolides?")],
    )
    question_ids = set(quiz.questions.values_list("pk", flat=True))
    answer_ids = set(
        QuizAnswer.objects.filter(question__quiz=quiz).values_list("pk", flat=True)
    )
    first_question = quiz.questions.order_by("position", "id").first()

    without_questions, _ = services.upsert_quiz(
        topic,
        title="Renamed",
        instance=quiz,
    )
    assert without_questions.title == "Renamed"
    assert set(without_questions.questions.values_list("pk", flat=True)) == question_ids
    assert (
        set(QuizAnswer.objects.filter(question__quiz=quiz).values_list("pk", flat=True))
        == answer_ids
    )

    partial, _ = services.upsert_quiz(
        topic,
        title="Renamed",
        instance=quiz,
        questions=[{"id": first_question.pk, "text": "Reworked", "answers": []}],
    )
    assert partial.questions.get(pk=first_question.pk).text == "Reworked"
    assert set(partial.questions.values_list("pk", flat=True)) == question_ids
    assert (
        set(QuizAnswer.objects.filter(question__quiz=quiz).values_list("pk", flat=True))
        == answer_ids
    )


@pytest.mark.django_db
def test_foreign_nested_quiz_ids_are_invalid_relations(topic, other_topic):
    other_quiz = services.save_quiz(other_topic, title="Other", questions=[_question()])
    foreign_question = other_quiz.questions.get()
    foreign_answer = foreign_question.answers.first()

    quiz, _ = services.upsert_quiz(topic, title="Basics", questions=[_question()])
    own_question = quiz.questions.get()

    with pytest.raises(APIError) as foreign_question_error:
        services.upsert_quiz(
            topic,
            title="Basics",
            instance=quiz,
            questions=[
                {"id": foreign_question.pk, "text": "Stolen", "answers": []},
            ],
        )
    assert foreign_question_error.value.default_code == "INVALID_RELATION"
    assert foreign_question_error.value.status_code == 422

    with pytest.raises(APIError) as foreign_answer_error:
        services.upsert_quiz(
            topic,
            title="Basics",
            instance=quiz,
            questions=[
                {
                    "id": own_question.pk,
                    "text": "Own",
                    "answers": [{"id": foreign_answer.pk, "text": "Stolen"}],
                },
            ],
        )
    assert foreign_answer_error.value.default_code == "INVALID_RELATION"
    assert foreign_answer_error.value.status_code == 422

    stored = QuizQuestion.objects.get(pk=foreign_question.pk)
    assert stored.text == "Which are beta-lactams?"
    assert QuizQuestion.objects.filter(pk=own_question.pk).exists()


@pytest.mark.django_db
def test_duplicate_explicit_positions_are_conflicts(topic):
    services.upsert_quiz(topic, title="Basics", position=1, questions=[_question()])

    with pytest.raises(APIError) as quiz_conflict:
        services.upsert_quiz(topic, title="Second", position=1, questions=[_question()])
    assert quiz_conflict.value.default_code == "CONTENT_CONFLICT"
    assert quiz_conflict.value.status_code == 409
    assert not Quiz.objects.filter(title="Second").exists()

    quiz, _ = services.upsert_quiz(topic, title="Third", questions=[_question()])

    with pytest.raises(APIError) as question_conflict:
        services.upsert_quiz(
            topic,
            title="Third",
            instance=quiz,
            questions=[
                {"text": "First", "position": 5, "answers": _question()["answers"]},
                {"text": "Second", "position": 5, "answers": _question()["answers"]},
            ],
        )
    assert question_conflict.value.default_code == "CONTENT_CONFLICT"
    assert question_conflict.value.status_code == 409

    with pytest.raises(APIError) as answer_conflict:
        services.upsert_quiz(
            topic,
            title="Third",
            instance=quiz,
            questions=[
                {
                    "text": "First",
                    "answers": [
                        {"text": "A", "is_correct": True, "position": 1},
                        {"text": "B", "position": 1},
                    ],
                },
            ],
        )
    assert answer_conflict.value.default_code == "CONTENT_CONFLICT"


@pytest.mark.django_db
def test_quiz_aggregate_invariants_are_conflicts(topic):
    with pytest.raises(APIError) as too_few_answers:
        services.upsert_quiz(
            topic,
            title="Thin",
            questions=[
                {"text": "Only one", "answers": [{"text": "A", "is_correct": True}]},
            ],
        )
    assert too_few_answers.value.default_code == "CONTENT_CONFLICT"
    assert too_few_answers.value.status_code == 409
    assert not Quiz.objects.filter(title="Thin").exists()

    quiz, _ = services.upsert_quiz(topic, title="Basics", questions=[_question()])
    question = quiz.questions.get()
    correct_answer = question.answers.get(is_correct=True)

    with pytest.raises(APIError) as no_correct_answer:
        services.upsert_quiz(
            topic,
            title="Basics",
            instance=quiz,
            questions=[
                {
                    "id": question.pk,
                    "text": question.text,
                    "answers": [
                        {
                            "id": correct_answer.pk,
                            "text": correct_answer.text,
                            "is_correct": False,
                        },
                    ],
                },
            ],
        )
    assert no_correct_answer.value.default_code == "CONTENT_CONFLICT"
    assert str(question.pk) in str(no_correct_answer.value.detail)
    assert QuizAnswer.objects.get(pk=correct_answer.pk).is_correct is True


@pytest.mark.django_db
def test_blank_quiz_child_text_is_a_validation_error(topic):
    with pytest.raises(APIError) as blank_question:
        services.upsert_quiz(
            topic,
            title="Basics",
            questions=[
                {"text": "   ", "answers": _question()["answers"]},
            ],
        )
    assert blank_question.value.default_code == "VALIDATION_ERROR"
    assert blank_question.value.status_code == 422

    with pytest.raises(APIError) as blank_answer:
        services.upsert_quiz(
            topic,
            title="Basics",
            questions=[
                {
                    "text": "Which are beta-lactams?",
                    "answers": [
                        {"text": "   ", "is_correct": True},
                        {"text": "Gentamicin"},
                    ],
                },
            ],
        )
    assert blank_answer.value.default_code == "VALIDATION_ERROR"
    assert not Quiz.objects.exists()


# ---------------------------------------------------------------------------
# Deletions.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_delete_subject_and_section_with_children_are_conflicts(catalog):
    subject = catalog["subject"]
    section = catalog["section"]
    topic = catalog["add_topic"](
        title="Beta-lactams",
        slug="beta-lactams",
        position=1,
    )

    with pytest.raises(APIError) as subject_conflict:
        services.delete_subject(subject)
    assert subject_conflict.value.default_code == "CONTENT_CONFLICT"
    assert subject_conflict.value.status_code == 409

    with pytest.raises(APIError) as section_conflict:
        services.delete_section(section)
    assert section_conflict.value.default_code == "CONTENT_CONFLICT"
    assert section_conflict.value.status_code == 409

    assert Subject.objects.filter(pk=subject.pk).exists()
    assert Section.objects.filter(pk=section.pk).exists()

    services.delete_topic(topic)
    services.delete_section(section)
    services.delete_subject(subject)

    assert not Section.objects.filter(pk=section.pk).exists()
    assert not Subject.objects.filter(pk=subject.pk).exists()


@pytest.mark.django_db
def test_delete_block_flashcard_and_quiz_remove_only_the_target(topic):
    block = services.save_content_block(
        topic,
        block_type_key="markdown",
        markdown_body="# Theory",
    )
    sibling_block = services.save_content_block(
        topic,
        block_type_key="markdown",
        markdown_body="# Other",
    )
    flashcard, _ = services.upsert_flashcard(
        topic,
        question="Which ring is strained?",
        answer="The beta-lactam ring",
    )
    quiz, _ = services.upsert_quiz(topic, title="Basics", questions=[_question()])

    services.delete_content_block(block)
    services.delete_flashcard(flashcard)
    services.delete_quiz(quiz)

    assert not ContentBlock.objects.filter(pk=block.pk).exists()
    assert ContentBlock.objects.filter(pk=sibling_block.pk).exists()
    assert not Flashcard.objects.filter(pk=flashcard.pk).exists()
    assert not Quiz.objects.filter(pk=quiz.pk).exists()
    assert not QuizQuestion.objects.filter(quiz_id=quiz.pk).exists()
    assert not QuizAnswer.objects.filter(question__quiz_id=quiz.pk).exists()
    assert Topic.objects.filter(pk=topic.pk).exists()


@pytest.mark.django_db
def test_a_duplicate_delete_of_a_vanished_row_is_404(topic):
    """The 004 delete paths answer 404 when the row vanished before the lock.

    A repeated ``DELETE`` whose first request committed while the second one was
    still between the read of its view and its row lock only discovers the
    vanished row under that lock.
    """

    block = services.save_content_block(
        topic,
        block_type_key="markdown",
        markdown_body="# Theory",
    )
    flashcard, _ = services.upsert_flashcard(
        topic,
        question="Which ring is strained?",
        answer="The beta-lactam ring",
    )

    services.delete_content_block(block)
    services.delete_flashcard(flashcard)

    with pytest.raises(APIError) as block_error:
        services.delete_content_block(block)
    assert (block_error.value.status_code, block_error.value.default_code) == (
        404,
        "RESOURCE_NOT_FOUND",
    )

    with pytest.raises(APIError) as flashcard_error:
        services.delete_flashcard(flashcard)
    assert (flashcard_error.value.status_code, flashcard_error.value.default_code) == (
        404,
        "RESOURCE_NOT_FOUND",
    )


@pytest.mark.django_db
def test_delete_source_removes_links_but_keeps_content(topic):
    flashcard, _ = services.upsert_flashcard(
        topic,
        question="Which ring is strained?",
        answer="The beta-lactam ring",
    )
    quiz, _ = services.upsert_quiz(topic, title="Basics", questions=[_question()])
    question = quiz.questions.get()

    source, _ = services.upsert_source(
        title="Guideline",
        source_type=Source.SourceType.GUIDELINE,
        topic_ids=[topic.pk],
        flashcard_ids=[flashcard.pk],
        question_ids=[question.pk],
    )
    assert source.topics.filter(pk=topic.pk).exists()
    assert source.flashcards.filter(pk=flashcard.pk).exists()
    assert source.questions.filter(pk=question.pk).exists()

    services.delete_source(source)

    assert not Source.objects.filter(pk=source.pk).exists()
    assert Topic.objects.filter(pk=topic.pk).exists()
    assert Flashcard.objects.filter(pk=flashcard.pk).exists()
    assert QuizQuestion.objects.filter(pk=question.pk).exists()


@pytest.mark.django_db
def test_topic_cascade_removes_flashcards_quizzes_and_their_children(topic):
    flashcard, _ = services.upsert_flashcard(
        topic,
        question="Which ring is strained?",
        answer="The beta-lactam ring",
    )
    quiz, _ = services.upsert_quiz(topic, title="Basics", questions=[_question()])
    question = quiz.questions.get()
    answer = question.answers.first()

    services.delete_topic(topic)

    assert not Flashcard.objects.filter(pk=flashcard.pk).exists()
    assert not Quiz.objects.filter(pk=quiz.pk).exists()
    assert not QuizQuestion.objects.filter(pk=question.pk).exists()
    assert not QuizAnswer.objects.filter(pk=answer.pk).exists()


# ---------------------------------------------------------------------------
# Source relation sets.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_source_relation_sets_replace_when_provided_and_keep_when_omitted(topic):
    first_card, _ = services.upsert_flashcard(
        topic,
        question="First",
        answer="A",
    )
    second_card, _ = services.upsert_flashcard(
        topic,
        question="Second",
        answer="B",
    )

    source, created = services.upsert_source(
        title="Textbook",
        source_type=Source.SourceType.TEXTBOOK,
        topic_ids=[topic.pk],
        flashcard_ids=[first_card.pk],
    )
    assert created is True
    assert set(source.topics.values_list("pk", flat=True)) == {topic.pk}
    assert set(source.flashcards.values_list("pk", flat=True)) == {first_card.pk}

    kept, _ = services.upsert_source(
        title="Textbook revised",
        source_type=Source.SourceType.TEXTBOOK,
        instance=source,
    )
    assert set(kept.topics.values_list("pk", flat=True)) == {topic.pk}
    assert set(kept.flashcards.values_list("pk", flat=True)) == {first_card.pk}

    replaced, _ = services.upsert_source(
        title="Textbook revised",
        source_type=Source.SourceType.TEXTBOOK,
        instance=source,
        topic_ids=[],
        flashcard_ids=[second_card.pk],
    )
    assert not replaced.topics.exists()
    assert set(replaced.flashcards.values_list("pk", flat=True)) == {second_card.pk}

    with pytest.raises(APIError) as unknown_topic:
        services.upsert_source(
            title="Textbook revised",
            source_type=Source.SourceType.TEXTBOOK,
            instance=source,
            topic_ids=[999999],
        )
    assert unknown_topic.value.default_code == "INVALID_RELATION"
    assert unknown_topic.value.status_code == 422

    with pytest.raises(APIError) as unknown_flashcard:
        services.upsert_source(
            title="Textbook revised",
            source_type=Source.SourceType.TEXTBOOK,
            instance=source,
            flashcard_ids=[999999],
        )
    assert unknown_flashcard.value.default_code == "INVALID_RELATION"
    assert Flashcard.objects.filter(pk=second_card.pk).exists()


# ---------------------------------------------------------------------------
# Concurrency.
# ---------------------------------------------------------------------------


class ConcurrentExternalIdUpsertTests(TransactionTestCase):
    """Two real transactions racing on one new external_id."""

    def test_concurrent_upsert_creates_one_row_and_one_conflict(self):
        barrier = threading.Barrier(2)
        resolve = services._resolve_upsert_target

        def synchronized_resolve(*args, **kwargs):
            # Both transactions resolve "no owner" before either inserts, so the
            # unique index (not scheduling luck) decides the winner.
            resolved = resolve(*args, **kwargs)
            barrier.wait(timeout=10)
            return resolved

        def upsert(index: int):
            try:
                subject, created = services.upsert_subject(
                    title=f"Subject {index}",
                    external_id="shared-external-id",
                    external_id_provided=True,
                )
                return ("created" if created else "updated", subject.pk)
            except APIError as exc:
                return ("error", exc.default_code)
            finally:
                connections.close_all()

        with mock.patch.object(
            services, "_resolve_upsert_target", synchronized_resolve
        ):
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(upsert, range(2)))

        self.assertEqual(
            Subject.objects.filter(external_id="shared-external-id").count(), 1
        )
        self.assertEqual(
            sorted(outcome for outcome, _ in results), ["created", "error"]
        )
        error = next(result for result in results if result[0] == "error")
        self.assertEqual(error[1], "EXTERNAL_ID_CONFLICT")
