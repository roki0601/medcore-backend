from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, models, transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone
from django.utils.text import slugify

from apps.common.exceptions import APIError
from apps.content.models import (
    ContentBlock,
    ContentBlockType,
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

MAX_SLUG_LENGTH = 255
EXTERNAL_ID_MAX_LENGTH = 255
SLUG_ATTEMPTS = 3
TEXT_BLOCK_KEYS = ("markdown", "callout")
IMAGE_BLOCK_KEY = "image"


def _unique_slug(model, title: str, *, instance=None) -> str:
    base = slugify(title)[:MAX_SLUG_LENGTH] or model._meta.model_name
    queryset = model.objects.all()
    if instance is not None and instance.pk is not None:
        queryset = queryset.exclude(pk=instance.pk)
    candidate = base
    suffix = 2
    while queryset.filter(slug=candidate).exists():
        tail = f"-{suffix}"
        candidate = f"{base[: MAX_SLUG_LENGTH - len(tail)]}{tail}"
        suffix += 1
    return candidate


def _next_position(model, parent, parent_field: str) -> int:
    queryset = model.objects.all()
    if parent is not None:
        queryset = queryset.filter(**{parent_field: parent})
    current = queryset.aggregate(value=models.Max("position"))["value"]
    return (current or 0) + 1


def _parent_changed(model, instance, parent, parent_field: str) -> bool:
    if instance.pk is None or parent is None or not parent_field:
        return False
    stored = (
        model.objects.filter(pk=instance.pk)
        .values_list(f"{parent_field}_id", flat=True)
        .first()
    )
    return stored is not None and stored != parent.pk


def _assert_position_free(
    model, instance, position: int, parent, parent_field: str
) -> None:
    conflict = model.objects.all()
    if parent is not None:
        conflict = conflict.filter(**{parent_field: parent})
    conflict = conflict.filter(position=position)
    if instance.pk is not None:
        conflict = conflict.exclude(pk=instance.pk)
    if conflict.exists():
        raise APIError(
            "Position is already in use.",
            code="CONTENT_CONFLICT",
            status_code=409,
        )


def _assign_position(model, instance, *, explicit_position, parent, parent_field):
    """Assign a deterministic position, re-assigning when the parent changed."""

    if instance.pk is None:
        if explicit_position is not None:
            _assert_position_free(
                model, instance, explicit_position, parent, parent_field
            )
            instance.position = explicit_position
        else:
            instance.position = _next_position(model, parent, parent_field)
        return
    if _parent_changed(model, instance, parent, parent_field):
        # Moving to another parent would keep a stale per-parent position.
        instance.position = _next_position(model, parent, parent_field)
        return
    if explicit_position is not None:
        _assert_position_free(model, instance, explicit_position, parent, parent_field)
        instance.position = explicit_position


def _validation_error(exc: DjangoValidationError) -> APIError:
    fields = getattr(exc, "message_dict", None) or {"non_field_errors": exc.messages}
    return APIError(
        "Request validation failed.",
        code="VALIDATION_ERROR",
        status_code=422,
        fields=fields,
    )


def _save_instance(instance, *, model, title: str, with_slug: bool = True):
    """Persist with a deterministic slug, retrying on a concurrent slug race."""

    last_error: IntegrityError | None = None
    for _ in range(SLUG_ATTEMPTS):
        if with_slug:
            instance.slug = _unique_slug(model, title, instance=instance)
        try:
            instance.full_clean(validate_unique=False, validate_constraints=False)
        except DjangoValidationError as exc:
            raise _validation_error(exc) from exc
        try:
            with transaction.atomic():
                instance.save()
            return instance
        except IntegrityError as exc:
            last_error = exc
    raise APIError(
        "Content conflict while saving.",
        code="CONTENT_CONFLICT",
        status_code=409,
    ) from last_error


def _stored_external_id(model, instance) -> str | None:
    """Read the persisted ``external_id`` of a row, not the in-memory value."""

    return (
        model.objects.filter(pk=instance.pk)
        .values_list("external_id", flat=True)
        .first()
    )


def _validate_external_id(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise APIError(
            "Request validation failed.",
            code="VALIDATION_ERROR",
            status_code=422,
            fields={"external_id": ["This field may not be blank."]},
        )
    if len(value) > EXTERNAL_ID_MAX_LENGTH:
        raise APIError(
            "Request validation failed.",
            code="VALIDATION_ERROR",
            status_code=422,
            fields={
                "external_id": [
                    "Ensure this field has no more than "
                    f"{EXTERNAL_ID_MAX_LENGTH} characters."
                ]
            },
        )
    return value


def _external_id_conflict(detail: str = "external_id is immutable.") -> APIError:
    return APIError(detail, code="EXTERNAL_ID_CONFLICT", status_code=409)


def _resolve_external_identity(
    model,
    *,
    instance,
    external_id: str | None,
    provided: bool,
) -> tuple[Any | None, bool]:
    """Decide which row an ``external_id`` write targets.

    ``external_id`` is one nullable identity per model, scoped to the single
    configured integration namespace (there is no per-tenant partitioning). An
    established value is immutable: an update may assign a value to a row that
    has none, but it can never change or clear one, which keeps repeated
    integration upserts addressing the same entity.

    ``provided`` distinguishes an absent key from an explicit ``null``/``""``
    because the transport layer is the only place that can tell them apart.

    Returns ``(target, created)``: ``target`` is the existing row to update, or
    ``None`` when the caller must create a row and assign the value.
    """

    is_new = instance is None or instance.pk is None
    if not provided:
        return instance, is_new

    if external_id is None or external_id == "":
        if not is_new and _stored_external_id(model, instance):
            raise _external_id_conflict()
        return instance, is_new

    value = _validate_external_id(external_id)
    if not is_new:
        stored = _stored_external_id(model, instance)
        if stored == value:
            return instance, False
        if stored is not None:
            raise _external_id_conflict()
        owner = model.objects.filter(external_id=value).exclude(pk=instance.pk).first()
        if owner is not None:
            raise _external_id_conflict("external_id is already in use.")
        instance.external_id = value
        return instance, False

    owner = model.objects.filter(external_id=value).first()
    if owner is not None:
        # POST upsert: an existing identity addresses that row instead of
        # creating a duplicate.
        return owner, False
    return None, True


def _is_external_id_violation(error: BaseException) -> bool:
    """Whether an ``IntegrityError`` chain is a uniqueness race on ``external_id``."""

    cause: BaseException | None = error
    for _ in range(4):
        if cause is None:
            return False
        diag = getattr(cause, "diag", None)
        name = getattr(diag, "constraint_name", None)
        if name:
            return "external_id" in str(name)
        cause = cause.__cause__
    return False


def _run_upsert_save(save_fn, /, **kwargs):
    """Persist through a save service, mapping an ``external_id`` race to 409.

    ``_save_instance`` already turns a uniqueness race into 409
    ``CONTENT_CONFLICT``; an ``external_id`` race must surface the documented
    ``EXTERNAL_ID_CONFLICT`` code instead, so the chained driver error is
    inspected. Every other conflict keeps the existing mapping.
    """

    try:
        return save_fn(**kwargs)
    except (APIError, IntegrityError) as exc:
        if _is_external_id_violation(exc):
            raise APIError(
                "external_id is already in use.",
                code="EXTERNAL_ID_CONFLICT",
                status_code=409,
            ) from exc
        if isinstance(exc, IntegrityError):
            raise APIError(
                "Content conflict while saving.",
                code="CONTENT_CONFLICT",
                status_code=409,
            ) from exc
        raise


def _resolve_upsert_target(model, *, instance, external_id, provided):
    """Resolve the row to write and materialize the value on a fresh row."""

    target, created = _resolve_external_identity(
        model,
        instance=instance,
        external_id=external_id,
        provided=provided,
    )
    if target is None:
        # An absent key and an explicit "" both mean "no identity": the stored
        # value is NULL, never a blank string.
        value = external_id if provided else None
        target = model(external_id=value or None)
    return target, created


def save_subject(
    *,
    title: str,
    description: str = "",
    position: int | None = None,
    cover=None,
    cover_provided: bool = False,
    instance: Subject | None = None,
) -> Subject:
    subject = instance or Subject()
    with transaction.atomic():
        subject.title = title
        subject.description = description
        if cover_provided:
            subject.cover = cover
        _assign_position(
            Subject,
            subject,
            explicit_position=position,
            parent=None,
            parent_field="",
        )
        return _save_instance(subject, model=Subject, title=title)


def save_section(
    subject: Subject,
    *,
    title: str,
    description: str = "",
    position: int | None = None,
    instance: Section | None = None,
) -> Section:
    section = instance or Section()
    with transaction.atomic():
        Subject.objects.select_for_update().get(pk=subject.pk)
        section.subject = subject
        section.title = title
        section.description = description
        _assign_position(
            Section,
            section,
            explicit_position=position,
            parent=subject,
            parent_field="subject",
        )
        return _save_instance(section, model=Section, title=title)


def save_topic(
    section: Section,
    *,
    title: str,
    description: str = "",
    position: int | None = None,
    status: str = Topic.Status.DRAFT,
    access_level: str = Topic.AccessLevel.DEMO,
    cover=None,
    cover_provided: bool = False,
    instance: Topic | None = None,
) -> Topic:
    topic = instance or Topic()
    with transaction.atomic():
        Section.objects.select_for_update().get(pk=section.pk)
        topic.section = section
        topic.title = title
        topic.description = description
        topic.status = status
        topic.access_level = access_level
        if cover_provided:
            topic.cover = cover
        _assign_position(
            Topic,
            topic,
            explicit_position=position,
            parent=section,
            parent_field="section",
        )
        return _save_instance(topic, model=Topic, title=title)


def publish_topic(topic: Topic) -> Topic:
    with transaction.atomic():
        locked = Topic.objects.select_for_update().get(pk=topic.pk)
        locked.status = Topic.Status.PUBLISHED
        locked.full_clean(validate_unique=False, validate_constraints=False)
        locked.save()
    return locked


def _not_found() -> APIError:
    return APIError("Resource not found.", code="RESOURCE_NOT_FOUND", status_code=404)


def _locked_row_or_404(model, pk: int):
    """Take the row lock of one row, mapping a row deleted meanwhile to 404.

    A repeated ``DELETE`` usually meets the read of the view, but a request that
    passed that read while another one committed the deletion only finds out
    here, under the lock.
    """

    try:
        return model.objects.select_for_update().get(pk=pk)
    except model.DoesNotExist as exc:
        raise _not_found() from exc


def _delete_locked_row(row) -> None:
    """Delete one already-locked row, mapping a PROTECT refusal to 409."""

    try:
        row.delete()
    except ProtectedError as exc:
        raise APIError(
            "Referenced by other content.",
            code="CONTENT_CONFLICT",
            status_code=409,
        ) from exc


def delete_topic(topic: Topic) -> None:
    """Delete the Topic aggregate and its owned children in one transaction."""

    with transaction.atomic():
        locked = Topic.objects.select_for_update().get(pk=topic.pk)
        _delete_locked_row(locked)


def resolve_block_type(block_type_key: str) -> ContentBlockType:
    try:
        return ContentBlockType.objects.get(key=block_type_key, active=True)
    except ContentBlockType.DoesNotExist as exc:
        raise APIError(
            "Unknown or inactive block type.",
            code="VALIDATION_ERROR",
            status_code=422,
        ) from exc


def _validate_publishable(block: ContentBlock) -> None:
    key = block.block_type.key
    if key in TEXT_BLOCK_KEYS:
        if not block.markdown_body.strip():
            raise APIError(
                "Markdown body is required for this block type.",
                code="INVALID_CONTENT_STATE",
                status_code=409,
            )
        return
    if key == IMAGE_BLOCK_KEY:
        if block.media is None:
            raise APIError(
                "A media reference is required for an image block.",
                code="INVALID_CONTENT_STATE",
                status_code=409,
            )
        return
    raise APIError(
        "Block type cannot be published.",
        code="INVALID_CONTENT_STATE",
        status_code=409,
    )


def _apply_status(block: ContentBlock, actor=None) -> None:
    if block.status == ContentBlock.Status.PUBLISHED:
        _validate_publishable(block)
        if block.published_at is None:
            block.published_at = timezone.now()
        if actor is not None and block.reviewed_by is None:
            block.reviewed_by = actor
    else:
        block.published_at = None


def _lock_media_reference(media) -> None:
    """Take the media row lock of a block reference, else 422 ``INVALID_RELATION``.

    Every block write that carries a media reference serializes on that media
    row, in the lock order the media deletion service uses (media row first,
    content rows second). A concurrent ``DELETE /api/v1/media/{id}/`` therefore
    either commits before this write — and the vanished row is refused here
    instead of the ``SET_NULL`` cascade detaching a freshly published reference —
    or waits until this write committed and then meets the content-owned deletion
    guard. The publish path of ``PATCH /api/v1/content/blocks/{id}/`` reaches
    this lock, so a published image block can never end up without its media.
    """

    if media is None:
        return
    if MediaFile.objects.select_for_update().filter(pk=media.pk).first() is None:
        raise APIError(
            "Unknown media.",
            code="INVALID_RELATION",
            status_code=422,
            fields={"media": ["Unknown relation id."]},
        )


def save_content_block(
    topic: Topic,
    *,
    block_type_key: str,
    markdown_body: str = "",
    media=None,
    caption: str = "",
    position: int | None = None,
    status: str = ContentBlock.Status.DRAFT,
    is_demo_preview: bool = False,
    actor=None,
    instance: ContentBlock | None = None,
) -> ContentBlock:
    block = instance or ContentBlock()
    block_type = resolve_block_type(block_type_key)
    with transaction.atomic():
        Topic.objects.select_for_update().get(pk=topic.pk)
        block.topic = topic
        block.block_type = block_type
        block.markdown_body = markdown_body
        block.media = media
        _lock_media_reference(block.media)
        block.caption = caption
        block.status = status
        block.is_demo_preview = is_demo_preview
        _assign_position(
            ContentBlock,
            block,
            explicit_position=position,
            parent=topic,
            parent_field="topic",
        )
        _apply_status(block, actor)
        return _save_instance(
            block,
            model=ContentBlock,
            title=topic.title,
            with_slug=False,
        )


def publish_content_block(block: ContentBlock, *, actor=None) -> ContentBlock:
    with transaction.atomic():
        # Lock the referenced media row before the block row, matching the lock
        # order used by the media deletion service. A concurrent delete of this
        # media therefore serializes against the publish instead of detaching a
        # freshly published image block.
        expected_media_id = (
            ContentBlock.objects.filter(pk=block.pk)
            .values_list("media_id", flat=True)
            .first()
        )
        if expected_media_id is not None:
            MediaFile.objects.select_for_update().filter(pk=expected_media_id).first()
        locked = ContentBlock.objects.select_for_update().get(pk=block.pk)
        if locked.media_id != expected_media_id:
            raise APIError(
                "The media reference changed while publishing.",
                code="CONTENT_CONFLICT",
                status_code=409,
            )
        locked.status = ContentBlock.Status.PUBLISHED
        _apply_status(locked, actor)
        locked.full_clean(validate_unique=False, validate_constraints=False)
        locked.save()
    return locked


def save_source(
    *,
    title: str,
    source_type: str,
    author: str = "",
    year: int | None = None,
    url: str = "",
    note: str = "",
    instance: Source | None = None,
) -> Source:
    source = instance or Source()
    source.title = title
    source.source_type = source_type
    source.author = author
    source.year = year
    source.url = url
    source.note = note
    try:
        source.full_clean(validate_unique=False, validate_constraints=False)
    except DjangoValidationError as exc:
        raise _validation_error(exc) from exc
    source.save()
    return source


def attach_source(
    source: Source,
    *,
    topic: Topic | None = None,
    block: ContentBlock | None = None,
) -> None:
    with transaction.atomic():
        if topic is not None:
            source.topics.add(topic)
        if block is not None:
            source.content_blocks.add(block)


def detach_source(
    source: Source,
    *,
    topic: Topic | None = None,
    block: ContentBlock | None = None,
) -> None:
    with transaction.atomic():
        if topic is not None:
            source.topics.remove(topic)
        if block is not None:
            source.content_blocks.remove(block)


# ---------------------------------------------------------------------------
# 004 write layer: flashcard/quiz services, deletions and external_id upserts.
# ---------------------------------------------------------------------------


def _resolve_relation_set(model, ids: Sequence[int], field: str) -> list[Any]:
    """Resolve an id list into rows, rejecting unknown ids as 422."""

    requested = list(dict.fromkeys(ids))
    if not requested:
        return []
    rows = {row.pk: row for row in model.objects.filter(pk__in=requested)}
    missing = [value for value in requested if value not in rows]
    if missing:
        raise APIError(
            f"Unknown {field}.",
            code="INVALID_RELATION",
            status_code=422,
            fields={field: ["Unknown relation id."]},
        )
    return [rows[value] for value in requested]


def save_flashcard(
    topic: Topic,
    *,
    question: str,
    answer: str,
    position: int | None = None,
    instance: Flashcard | None = None,
) -> Flashcard:
    flashcard = instance or Flashcard()
    with transaction.atomic():
        Topic.objects.select_for_update().get(pk=topic.pk)
        flashcard.topic = topic
        flashcard.question = question
        flashcard.answer = answer
        _assign_position(
            Flashcard,
            flashcard,
            explicit_position=position,
            parent=topic,
            parent_field="topic",
        )
        return _save_instance(
            flashcard,
            model=Flashcard,
            title=question,
            with_slug=False,
        )


def delete_flashcard(flashcard: Flashcard) -> None:
    """Delete one Flashcard in one transaction, leaving Source links behind."""

    with transaction.atomic():
        locked = _locked_row_or_404(Flashcard, flashcard.pk)
        _delete_locked_row(locked)


def _locked_quiz_child(model, pk: int, parent_filter: Mapping[str, Any], label: str):
    """Fetch a nested row scoped to its parent, else 422 ``INVALID_RELATION``."""

    row = model.objects.select_for_update().filter(pk=pk, **parent_filter).first()
    if row is None:
        raise APIError(
            f"Unknown {label.lower()}.",
            code="INVALID_RELATION",
            status_code=422,
            fields={"id": [f"The {label.lower()} does not belong to this quiz."]},
        )
    return row


def _sync_quiz_answers(
    question: QuizQuestion,
    answers: Sequence[Mapping[str, Any]],
) -> None:
    """Upsert answers of one question; omitted answers are never deleted."""

    for item in answers:
        text = item.get("text")
        position = item.get("position")
        answer_id = item.get("id")
        if answer_id is None:
            answer = QuizAnswer(question=question, text=text)
        else:
            answer = _locked_quiz_child(
                QuizAnswer,
                answer_id,
                {"question": question},
                "Answer",
            )
            if text is not None:
                answer.text = text
        if "is_correct" in item:
            answer.is_correct = bool(item["is_correct"])
        _assign_position(
            QuizAnswer,
            answer,
            explicit_position=position,
            parent=question,
            parent_field="question",
        )
        _save_instance(
            answer,
            model=QuizAnswer,
            title=text or "",
            with_slug=False,
        )


def _sync_quiz_questions(
    quiz: Quiz,
    questions: Sequence[Mapping[str, Any]],
) -> None:
    """Upsert nested questions and answers; omitted children are never deleted.

    Items carrying an ``id`` are updated in place (the row id is preserved) and
    must belong to the addressed quiz; items without an ``id`` are created.
    """

    for item in questions:
        text = item.get("text")
        position = item.get("position")
        question_id = item.get("id")
        if question_id is None:
            question = QuizQuestion(quiz=quiz, text=text)
        else:
            question = _locked_quiz_child(
                QuizQuestion,
                question_id,
                {"quiz": quiz},
                "Question",
            )
            if text is not None:
                question.text = text
        _assign_position(
            QuizQuestion,
            question,
            explicit_position=position,
            parent=quiz,
            parent_field="quiz",
        )
        question = _save_instance(
            question,
            model=QuizQuestion,
            title=text or "",
            with_slug=False,
        )
        _sync_quiz_answers(question, item.get("answers") or ())


def _validate_quiz_aggregate(quiz: Quiz) -> None:
    """Enforce the quiz aggregate invariants on the persisted rows."""

    questions = list(quiz.questions.order_by("position", "id"))
    if not questions:
        raise APIError(
            "A quiz must keep at least one question.",
            code="CONTENT_CONFLICT",
            status_code=409,
        )
    for question in questions:
        if not (question.text or "").strip():
            raise APIError(
                f"Question {question.pk} must have non-blank text.",
                code="CONTENT_CONFLICT",
                status_code=409,
            )
        answers = list(question.answers.order_by("position", "id"))
        if len(answers) < 2:
            raise APIError(
                f"Question {question.pk} must keep at least two answers.",
                code="CONTENT_CONFLICT",
                status_code=409,
            )
        if not any(answer.is_correct for answer in answers):
            raise APIError(
                f"Question {question.pk} must keep at least one correct answer.",
                code="CONTENT_CONFLICT",
                status_code=409,
            )
        for answer in answers:
            if not (answer.text or "").strip():
                raise APIError(
                    f"Answer {answer.pk} must have non-blank text.",
                    code="CONTENT_CONFLICT",
                    status_code=409,
                )


def save_quiz(
    topic: Topic,
    *,
    title: str,
    description: str = "",
    position: int | None = None,
    questions: Sequence[Mapping[str, Any]] | None = None,
    instance: Quiz | None = None,
) -> Quiz:
    """Write the whole quiz aggregate in one transaction.

    ``questions is None`` leaves the persisted questions and answers untouched;
    otherwise the nested payload is upserted by id and the resulting aggregate
    is validated.
    """

    quiz = instance or Quiz()
    with transaction.atomic():
        Topic.objects.select_for_update().get(pk=topic.pk)
        quiz.topic = topic
        quiz.title = title
        quiz.description = description
        _assign_position(
            Quiz,
            quiz,
            explicit_position=position,
            parent=topic,
            parent_field="topic",
        )
        quiz = _save_instance(quiz, model=Quiz, title=title, with_slug=False)
        if questions is not None:
            _sync_quiz_questions(quiz, questions)
            _validate_quiz_aggregate(quiz)
        return quiz


def delete_quiz(quiz: Quiz) -> None:
    """Delete one Quiz with its questions and answers in one transaction."""

    with transaction.atomic():
        locked = _locked_row_or_404(Quiz, quiz.pk)
        _delete_locked_row(locked)


def delete_subject(subject: Subject) -> None:
    """Delete one Subject; a Subject that still owns Sections is refused."""

    with transaction.atomic():
        locked = _locked_row_or_404(Subject, subject.pk)
        _delete_locked_row(locked)


def delete_section(section: Section) -> None:
    """Delete one Section; a Section that still owns Topics is refused."""

    with transaction.atomic():
        locked = _locked_row_or_404(Section, section.pk)
        _delete_locked_row(locked)


def delete_content_block(block: ContentBlock) -> None:
    """Delete one ContentBlock in one transaction."""

    with transaction.atomic():
        locked = _locked_row_or_404(ContentBlock, block.pk)
        _delete_locked_row(locked)


def delete_source(source: Source) -> None:
    """Delete one Source row; M2M links cascade and content is never deleted."""

    with transaction.atomic():
        locked = _locked_row_or_404(Source, source.pk)
        _delete_locked_row(locked)


def upsert_subject(
    *,
    title: str,
    description: str = "",
    position: int | None = None,
    cover=None,
    cover_provided: bool = False,
    external_id: str | None = None,
    external_id_provided: bool = False,
    instance: Subject | None = None,
) -> tuple[Subject, bool]:
    """Create or update a Subject, upserting by ``external_id``."""

    with transaction.atomic():
        target, created = _resolve_upsert_target(
            Subject,
            instance=instance,
            external_id=external_id,
            provided=external_id_provided,
        )
        subject = _run_upsert_save(
            save_subject,
            title=title,
            description=description,
            position=position,
            cover=cover,
            cover_provided=cover_provided,
            instance=target,
        )
        return subject, created


def upsert_section(
    subject: Subject,
    *,
    title: str,
    description: str = "",
    position: int | None = None,
    external_id: str | None = None,
    external_id_provided: bool = False,
    instance: Section | None = None,
) -> tuple[Section, bool]:
    """Create or update a Section, upserting by ``external_id``."""

    with transaction.atomic():
        target, created = _resolve_upsert_target(
            Section,
            instance=instance,
            external_id=external_id,
            provided=external_id_provided,
        )
        section = _run_upsert_save(
            save_section,
            subject=subject,
            title=title,
            description=description,
            position=position,
            instance=target,
        )
        return section, created


def upsert_topic(
    section: Section,
    *,
    title: str,
    description: str = "",
    position: int | None = None,
    status: str = Topic.Status.DRAFT,
    access_level: str = Topic.AccessLevel.DEMO,
    cover=None,
    cover_provided: bool = False,
    external_id: str | None = None,
    external_id_provided: bool = False,
    instance: Topic | None = None,
) -> tuple[Topic, bool]:
    """Create or update a Topic, upserting by ``external_id``."""

    with transaction.atomic():
        target, created = _resolve_upsert_target(
            Topic,
            instance=instance,
            external_id=external_id,
            provided=external_id_provided,
        )
        topic = _run_upsert_save(
            save_topic,
            section=section,
            title=title,
            description=description,
            position=position,
            status=status,
            access_level=access_level,
            cover=cover,
            cover_provided=cover_provided,
            instance=target,
        )
        return topic, created


def upsert_content_block(
    topic: Topic,
    *,
    block_type_key: str,
    markdown_body: str = "",
    media=None,
    caption: str = "",
    position: int | None = None,
    status: str = ContentBlock.Status.DRAFT,
    is_demo_preview: bool = False,
    external_id: str | None = None,
    external_id_provided: bool = False,
    actor=None,
    instance: ContentBlock | None = None,
) -> tuple[ContentBlock, bool]:
    """Create or update a ContentBlock, upserting by ``external_id``."""

    with transaction.atomic():
        target, created = _resolve_upsert_target(
            ContentBlock,
            instance=instance,
            external_id=external_id,
            provided=external_id_provided,
        )
        block = _run_upsert_save(
            save_content_block,
            topic=topic,
            block_type_key=block_type_key,
            markdown_body=markdown_body,
            media=media,
            caption=caption,
            position=position,
            status=status,
            is_demo_preview=is_demo_preview,
            actor=actor,
            instance=target,
        )
        return block, created


def upsert_flashcard(
    topic: Topic,
    *,
    question: str,
    answer: str,
    position: int | None = None,
    external_id: str | None = None,
    external_id_provided: bool = False,
    instance: Flashcard | None = None,
) -> tuple[Flashcard, bool]:
    """Create or update a Flashcard, upserting by ``external_id``."""

    with transaction.atomic():
        target, created = _resolve_upsert_target(
            Flashcard,
            instance=instance,
            external_id=external_id,
            provided=external_id_provided,
        )
        flashcard = _run_upsert_save(
            save_flashcard,
            topic=topic,
            question=question,
            answer=answer,
            position=position,
            instance=target,
        )
        return flashcard, created


def upsert_quiz(
    topic: Topic,
    *,
    title: str,
    description: str = "",
    position: int | None = None,
    questions: Sequence[Mapping[str, Any]] | None = None,
    external_id: str | None = None,
    external_id_provided: bool = False,
    instance: Quiz | None = None,
) -> tuple[Quiz, bool]:
    """Create or update a Quiz aggregate, upserting by ``external_id``."""

    with transaction.atomic():
        target, created = _resolve_upsert_target(
            Quiz,
            instance=instance,
            external_id=external_id,
            provided=external_id_provided,
        )
        quiz = _run_upsert_save(
            save_quiz,
            topic=topic,
            title=title,
            description=description,
            position=position,
            questions=questions,
            instance=target,
        )
        return quiz, created


def upsert_source(
    *,
    title: str,
    source_type: str,
    author: str = "",
    year: int | None = None,
    url: str = "",
    note: str = "",
    topic_ids: Sequence[int] | None = None,
    block_ids: Sequence[int] | None = None,
    flashcard_ids: Sequence[int] | None = None,
    question_ids: Sequence[int] | None = None,
    external_id: str | None = None,
    external_id_provided: bool = False,
    instance: Source | None = None,
) -> tuple[Source, bool]:
    """Create or update a Source, upserting by ``external_id``.

    Each relation id list is set semantics: when provided it becomes the
    complete relation set, when omitted the existing relations stay untouched.
    """

    with transaction.atomic():
        target, created = _resolve_upsert_target(
            Source,
            instance=instance,
            external_id=external_id,
            provided=external_id_provided,
        )
        source = _run_upsert_save(
            save_source,
            title=title,
            source_type=source_type,
            author=author,
            year=year,
            url=url,
            note=note,
            instance=target,
        )
        if topic_ids is not None:
            source.topics.set(_resolve_relation_set(Topic, topic_ids, "topic_ids"))
        if block_ids is not None:
            source.content_blocks.set(
                _resolve_relation_set(ContentBlock, block_ids, "block_ids")
            )
        if flashcard_ids is not None:
            source.flashcards.set(
                _resolve_relation_set(Flashcard, flashcard_ids, "flashcard_ids")
            )
        if question_ids is not None:
            source.questions.set(
                _resolve_relation_set(QuizQuestion, question_ids, "question_ids")
            )
        return source, created
