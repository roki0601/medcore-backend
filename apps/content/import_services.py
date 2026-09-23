from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from pydantic import ValidationError as PydanticValidationError

from apps.common.exceptions import APIError
from apps.content import services
from apps.content.import_schemas import (
    ImportStudyDocument,
    format_validation_error,
)
from apps.content.models import (
    ContentBlock,
    ContentBlockType,
    Flashcard,
    Quiz,
    Section,
    Topic,
)
from apps.content.slugs import latin_base


@dataclass(frozen=True)
class ImportResult:
    topic: Topic
    blocks_count: int
    flashcards_count: int
    questions_count: int
    answers_count: int
    created: bool


class ContentImportError(Exception):
    """Human-readable exception during content import."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def validate_and_parse_document(raw_data: dict[str, Any]) -> ImportStudyDocument:
    """Validate and parse raw dictionary into ImportStudyDocument.

    Produces human-readable error messages for validation failures.
    """
    try:
        return ImportStudyDocument.model_validate(raw_data)
    except PydanticValidationError as exc:
        raise ContentImportError(format_validation_error(exc.errors())) from exc


def import_study_document(
    document: ImportStudyDocument | dict[str, Any],
    *,
    section: Section,
    position: int | None = None,
    status: str = Topic.Status.DRAFT,
    access_level: str = Topic.AccessLevel.DEMO,
    actor=None,
) -> ImportResult:
    """Import or update topic, blocks, flashcards, and quiz from a validated document.

    All writes are executed atomically inside a single transaction.
    If any error occurs, the transaction rolls back cleanly.

    Positional matching limitation:
    Child entities (ContentBlock, Flashcard, QuizQuestion, QuizAnswer) are
    matched and updated by ordinal position (1..N). This preserves primary keys
    only for elements remaining at the same position. Insertions or reordering
    can semantically rebind an existing PK to new content at that position.
    """
    if isinstance(document, dict):
        doc = validate_and_parse_document(document)
    else:
        doc = document

    topic_title = (doc.content.title or doc.topic or "").strip()
    if not topic_title:
        raise ContentImportError("Topic title cannot be blank.")

    # 1. Check all required block types exist and are active
    for block in doc.content.blocks:
        if not ContentBlockType.objects.filter(
            key=block.block_type, active=True
        ).exists():
            raise ContentImportError(
                f'ContentBlockType "{block.block_type}" does not exist.'
            )

    # 2. Derive stable external_id scoped to Section identity
    if doc.external_id and doc.external_id.strip():
        topic_external_id = doc.external_id.strip()[:255]
    else:
        section_identity = (
            section.external_id.strip()
            if section.external_id and section.external_id.strip()
            else str(section.pk)
        )
        topic_slug = latin_base(topic_title, fallback="topic")
        topic_external_id = f"medcore-content:topic:{section_identity}:{topic_slug}"[
            :255
        ]

    try:
        with transaction.atomic():
            # Lock section row to prevent concurrency anomalies
            Section.objects.select_for_update().get(pk=section.pk)

            # 3. Create or update Topic
            existing_topic = Topic.objects.filter(external_id=topic_external_id).first()
            topic, topic_created = services.upsert_topic(
                section=section,
                title=topic_title,
                description=existing_topic.description if existing_topic else "",
                position=position,
                status=status,
                access_level=access_level,
                external_id=topic_external_id,
                external_id_provided=True,
                instance=existing_topic,
            )

            # 4. Upsert Content Blocks
            block_status = (
                ContentBlock.Status.PUBLISHED
                if status == Topic.Status.PUBLISHED
                else ContentBlock.Status.DRAFT
            )

            for idx, block_data in enumerate(doc.content.blocks):
                pos = idx + 1
                block_external_id = f"{topic_external_id}:block:{pos}"[:255]
                services.upsert_content_block(
                    topic=topic,
                    block_type_key=block_data.block_type,
                    markdown_body=block_data.markdown_body,
                    caption=block_data.caption,
                    position=pos,
                    status=block_status,
                    external_id=block_external_id,
                    external_id_provided=True,
                    actor=actor,
                )

            # Remove extra previously imported blocks of this topic
            stale_block_prefix = f"{topic_external_id}:block:"
            stale_blocks = ContentBlock.objects.filter(
                topic=topic,
                external_id__startswith=stale_block_prefix,
                position__gt=len(doc.content.blocks),
            )
            for stale_b in stale_blocks:
                services.delete_content_block(stale_b)

            # 5. Upsert Flashcards
            for idx, card_data in enumerate(doc.flashcards):
                pos = idx + 1
                card_external_id = f"{topic_external_id}:flashcard:{pos}"[:255]
                services.upsert_flashcard(
                    topic=topic,
                    question=card_data.question,
                    answer=card_data.answer,
                    position=pos,
                    external_id=card_external_id,
                    external_id_provided=True,
                )

            # Remove extra previously imported flashcards of this topic
            stale_card_prefix = f"{topic_external_id}:flashcard:"
            stale_cards = Flashcard.objects.filter(
                topic=topic,
                external_id__startswith=stale_card_prefix,
                position__gt=len(doc.flashcards),
            )
            for stale_fc in stale_cards:
                services.delete_flashcard(stale_fc)

            # 6. Upsert Quiz
            questions_count = 0
            answers_count = 0
            if doc.quiz and doc.quiz.questions:
                quiz_external_id = f"{topic_external_id}:quiz"[:255]
                existing_quiz = Quiz.objects.filter(
                    external_id=quiz_external_id
                ).first()

                existing_questions = []
                if existing_quiz is not None:
                    existing_questions = list(
                        existing_quiz.questions.order_by("position", "id")
                    )

                prepared_questions = []
                for q_idx, q_data in enumerate(doc.quiz.questions):
                    q_pos = q_idx + 1
                    q_dict: dict[str, Any] = {
                        "text": q_data.text,
                        "position": q_pos,
                    }
                    existing_q = (
                        existing_questions[q_idx]
                        if q_idx < len(existing_questions)
                        else None
                    )
                    if existing_q is not None:
                        q_dict["id"] = existing_q.pk
                        existing_answers = list(
                            existing_q.answers.order_by("position", "id")
                        )
                    else:
                        existing_answers = []

                    prepared_answers = []
                    for a_idx, a_data in enumerate(q_data.answers):
                        a_pos = a_idx + 1
                        a_dict: dict[str, Any] = {
                            "text": a_data.text,
                            "is_correct": a_data.is_correct,
                            "position": a_pos,
                        }
                        if a_idx < len(existing_answers):
                            a_dict["id"] = existing_answers[a_idx].pk
                        prepared_answers.append(a_dict)

                    # Delete extra answers on existing question
                    if len(existing_answers) > len(q_data.answers):
                        for extra_a in existing_answers[len(q_data.answers) :]:
                            extra_a.delete()

                    q_dict["answers"] = prepared_answers
                    prepared_questions.append(q_dict)

                # Delete extra questions on existing quiz
                if len(existing_questions) > len(doc.quiz.questions):
                    for extra_q in existing_questions[len(doc.quiz.questions) :]:
                        extra_q.delete()

                quiz_title = (doc.quiz.title or topic_title).strip()
                quiz_desc = (doc.quiz.description or "").strip()

                services.upsert_quiz(
                    topic=topic,
                    title=quiz_title,
                    description=quiz_desc,
                    position=existing_quiz.position if existing_quiz else 1,
                    questions=prepared_questions,
                    external_id=quiz_external_id,
                    external_id_provided=True,
                    instance=existing_quiz,
                )
                questions_count = len(doc.quiz.questions)
                answers_count = sum(len(q.answers) for q in doc.quiz.questions)

            return ImportResult(
                topic=topic,
                blocks_count=len(doc.content.blocks),
                flashcards_count=len(doc.flashcards),
                questions_count=questions_count,
                answers_count=answers_count,
                created=topic_created,
            )
    except APIError as exc:
        raise ContentImportError(exc.detail) from exc
    except DjangoValidationError as exc:
        msg = ", ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
        raise ContentImportError(msg) from exc
