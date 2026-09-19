from __future__ import annotations

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.content.models import ContentBlock, Topic
from apps.learning.models import (
    FlashcardReview,
    QuizAttempt,
    UserTopicBlockProgress,
    UserTopicProgress,
)


def _graph(
    *,
    make_user,
    make_topic,
    make_block,
    make_flashcard,
    make_quiz,
    make_quiz_question,
    make_quiz_answer,
    user=None,
    topic=None,
    access_level: str = Topic.AccessLevel.DEMO,
):
    """One user plus one learning row of each model over a real content graph."""

    user = user or make_user()
    topic = topic or make_topic(access_level=access_level)
    block = make_block(topic)
    flashcard = make_flashcard(topic)
    quiz = make_quiz(topic)
    question = make_quiz_question(quiz)
    make_quiz_answer(question, is_correct=True)
    make_quiz_answer(question)
    rows = {
        "topic_progress": UserTopicProgress.objects.create(user=user, topic=topic),
        "block_progress": UserTopicBlockProgress.objects.create(
            user=user,
            block=block,
            is_complete=True,
            completed_at=timezone.now(),
        ),
        "review": FlashcardReview.objects.create(user=user, flashcard=flashcard),
        "attempt": QuizAttempt.objects.create(
            user=user,
            quiz=quiz,
            question_ids=[question.id],
        ),
    }
    return {
        "user": user,
        "topic": topic,
        "block": block,
        "flashcard": flashcard,
        "quiz": quiz,
        "question": question,
        **rows,
    }


def _learning_row_counts() -> dict[str, int]:
    return {
        "topic_progress": UserTopicProgress.objects.count(),
        "block_progress": UserTopicBlockProgress.objects.count(),
        "review": FlashcardReview.objects.count(),
        "attempt": QuizAttempt.objects.count(),
    }


@pytest.mark.django_db
def test_topic_progress_is_unique_per_user_and_topic(make_user, make_topic):
    user = make_user()
    topic = make_topic()
    UserTopicProgress.objects.create(user=user, topic=topic)

    with pytest.raises(IntegrityError), transaction.atomic():
        UserTopicProgress.objects.create(user=user, topic=topic)


@pytest.mark.django_db
def test_block_progress_is_unique_per_user_and_block(
    make_user,
    make_topic,
    make_block,
):
    user = make_user()
    block = make_block(make_topic())
    UserTopicBlockProgress.objects.create(user=user, block=block)

    with pytest.raises(IntegrityError), transaction.atomic():
        UserTopicBlockProgress.objects.create(user=user, block=block)


@pytest.mark.django_db
def test_topic_progress_status_is_protected_by_the_check_constraint(
    make_user,
    make_topic,
):
    progress = UserTopicProgress.objects.create(user=make_user(), topic=make_topic())

    with pytest.raises(IntegrityError), transaction.atomic():
        UserTopicProgress.objects.filter(pk=progress.pk).update(status="completed")


@pytest.mark.django_db
def test_attempt_status_is_protected_by_the_check_constraint(
    make_user,
    make_topic,
    make_quiz,
):
    attempt = QuizAttempt.objects.create(user=make_user(), quiz=make_quiz(make_topic()))

    with pytest.raises(IntegrityError), transaction.atomic():
        QuizAttempt.objects.filter(pk=attempt.pk).update(status="finished")


@pytest.mark.django_db
@pytest.mark.parametrize("score_percent", [-1, 101])
def test_attempt_score_is_bounded_by_the_check_constraint(
    score_percent,
    make_user,
    make_topic,
    make_quiz,
):
    with pytest.raises(IntegrityError), transaction.atomic():
        QuizAttempt.objects.create(
            user=make_user(),
            quiz=make_quiz(make_topic()),
            score_percent=score_percent,
        )


@pytest.mark.django_db
def test_only_one_active_attempt_exists_per_user_and_quiz(
    make_user,
    make_topic,
    make_quiz,
):
    user = make_user()
    quiz = make_quiz(make_topic())
    QuizAttempt.objects.create(user=user, quiz=quiz, status=QuizAttempt.Status.ACTIVE)

    with pytest.raises(IntegrityError), transaction.atomic():
        QuizAttempt.objects.create(
            user=user,
            quiz=quiz,
            status=QuizAttempt.Status.ACTIVE,
        )


@pytest.mark.django_db
def test_submitted_attempts_do_not_block_new_active_or_repeat_attempts(
    make_user,
    make_topic,
    make_quiz,
):
    """The partial unique constraint covers ``active`` rows only, so retakes survive."""

    user = make_user()
    quiz = make_quiz(make_topic())
    QuizAttempt.objects.create(
        user=user,
        quiz=quiz,
        status=QuizAttempt.Status.SUBMITTED,
        submitted_at=timezone.now(),
    )
    QuizAttempt.objects.create(
        user=user,
        quiz=quiz,
        status=QuizAttempt.Status.SUBMITTED,
        submitted_at=timezone.now(),
    )
    QuizAttempt.objects.create(user=user, quiz=quiz, status=QuizAttempt.Status.ACTIVE)

    assert QuizAttempt.objects.filter(quiz=quiz).count() == 3


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("model", "forbidden_field"),
    [(UserTopicBlockProgress, "topic"), (QuizAttempt, "passed")],
)
def test_learning_models_keep_no_stale_column(model, forbidden_field):
    """The accepted data model has no stored block topic and no pass flag."""

    field_names = {field.name for field in model._meta.concrete_fields}
    assert forbidden_field not in field_names


@pytest.mark.django_db
def test_user_deletion_cascades_every_learning_row(
    make_user,
    make_topic,
    make_block,
    make_flashcard,
    make_quiz,
    make_quiz_question,
    make_quiz_answer,
):
    graph = _graph(
        make_user=make_user,
        make_topic=make_topic,
        make_block=make_block,
        make_flashcard=make_flashcard,
        make_quiz=make_quiz,
        make_quiz_question=make_quiz_question,
        make_quiz_answer=make_quiz_answer,
    )
    assert _learning_row_counts() == {
        "topic_progress": 1,
        "block_progress": 1,
        "review": 1,
        "attempt": 1,
    }

    graph["user"].delete()

    assert _learning_row_counts() == {
        "topic_progress": 0,
        "block_progress": 0,
        "review": 0,
        "attempt": 0,
    }


@pytest.mark.django_db
def test_topic_deletion_cascades_every_learning_row_of_that_topic(
    make_user,
    make_topic,
    make_block,
    make_flashcard,
    make_quiz,
    make_quiz_question,
    make_quiz_answer,
):
    graph = _graph(
        make_user=make_user,
        make_topic=make_topic,
        make_block=make_block,
        make_flashcard=make_flashcard,
        make_quiz=make_quiz,
        make_quiz_question=make_quiz_question,
        make_quiz_answer=make_quiz_answer,
    )

    graph["topic"].delete()

    assert _learning_row_counts() == {
        "topic_progress": 0,
        "block_progress": 0,
        "review": 0,
        "attempt": 0,
    }


@pytest.mark.django_db
def test_content_deletion_removes_only_its_own_learning_row(
    make_user,
    make_topic,
    make_block,
    make_flashcard,
    make_quiz,
    make_quiz_question,
    make_quiz_answer,
):
    graph = _graph(
        make_user=make_user,
        make_topic=make_topic,
        make_block=make_block,
        make_flashcard=make_flashcard,
        make_quiz=make_quiz,
        make_quiz_question=make_quiz_question,
        make_quiz_answer=make_quiz_answer,
    )

    graph["block"].delete()
    assert _learning_row_counts() == {
        "topic_progress": 1,
        "block_progress": 0,
        "review": 1,
        "attempt": 1,
    }

    graph["flashcard"].delete()
    assert _learning_row_counts() == {
        "topic_progress": 1,
        "block_progress": 0,
        "review": 0,
        "attempt": 1,
    }

    graph["quiz"].delete()
    assert _learning_row_counts() == {
        "topic_progress": 1,
        "block_progress": 0,
        "review": 0,
        "attempt": 0,
    }
    orphans = UserTopicBlockProgress.objects.filter(block_id=graph["block"].pk)
    assert orphans.count() == 0


@pytest.mark.django_db
def test_block_re_parented_to_another_topic_keeps_its_single_row(
    make_user,
    make_topic,
    make_block,
):
    """The topic is derived from the block, so a re-parent cannot leave a stale pair."""

    user = make_user()
    original = make_topic(title="Original")
    target = make_topic(title="Target")
    block = make_block(original)
    UserTopicBlockProgress.objects.create(user=user, block=block, is_complete=True)

    ContentBlock.objects.filter(pk=block.pk).update(topic=target)

    row = UserTopicBlockProgress.objects.get(user=user)
    assert row.block.topic_id == target.pk
    assert UserTopicBlockProgress.objects.filter(block__topic=original).count() == 0
    assert UserTopicBlockProgress.objects.filter(block__topic=target).count() == 1
