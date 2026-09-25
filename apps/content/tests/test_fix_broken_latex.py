from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command

from apps.content.management.commands.fix_broken_latex import (
    fix_latex_text,
)
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


@pytest.mark.parametrize(
    ("damaged", "expected_fixed", "expected_label", "expected_count"),
    [
        ("$O_2^{\x08ullet-}$", r"$O_2^{\bullet-}$", r"\bullet", 1),
        (r"$O_2^{\x08ullet-}$", r"$O_2^{\bullet-}$", r"\bullet", 1),
        ("A \r" + "ightarrow B", r"A \rightarrow B", r"\rightarrow", 1),
        ("$" + "\t" + "ext{hello}$", r"$\text{hello}$", r"\text", 1),
        ("$\x0crac{a}{b}$", r"$\frac{a}{b}$", r"\frac", 1),
        (r"$\x0crac{a}{b}$", r"$\frac{a}{b}$", r"\frac", 1),
        ("\r" + "ight)", r"\right)", r"\right", 1),
        ("$\x08eta$-blocker", r"$\beta$-blocker", r"\beta", 1),
        (r"$\x08eta$-blocker", r"$\beta$-blocker", r"\beta", 1),
        ("\x08egin{matrix}", r"\begin{matrix}", r"\begin", 1),
        ("\x08ar{x}", r"\bar{x}", r"\bar", 1),
        ("5 " + "\t" + "imes 10", r"5 \times 10", r"\times", 1),
        ("\t" + "heta rhythm", r"\theta rhythm", r"\theta", 1),
        ("\t" + "au protein", r"\tau protein", r"\tau", 1),
        ("\r" + "ho factor", r"\rho factor", r"\rho", 1),
        ("\x0corall x", r"\forall x", r"\forall", 1),
        (r"\x0corall x", r"\forall x", r"\forall", 1),
    ],
)
def test_fix_latex_text_individual_signatures(
    damaged: str,
    expected_fixed: str,
    expected_label: str,
    expected_count: int,
) -> None:
    fixed, counts = fix_latex_text(damaged)
    assert fixed == expected_fixed
    assert counts.get(expected_label) == expected_count


def test_fix_latex_text_preserves_plain_text_and_crlf() -> None:
    plain_text = (
        "bullet point about text and fraction with rightarrow\r\n"
        "extra line without control character damage.\r\n"
        "another line with tab\tregular_word."
    )
    fixed, counts = fix_latex_text(plain_text)
    assert fixed == plain_text
    assert counts == {}


def test_fix_latex_text_multiple_replacements() -> None:
    # chr(8) + ullet, chr(13) + ightarrow, chr(12) + rac, chr(9) + ext
    mixed = (
        "$O_2^{\x08ullet-} "
        + "\r"
        + "ightarrow "
        + "\x0c"
        + "rac{1}{2} "
        + "\t"
        + "ext{mg}$"
    )
    expected = r"$O_2^{\bullet-} \rightarrow \frac{1}{2} \text{mg}$"
    fixed, counts = fix_latex_text(mixed)
    assert fixed == expected
    assert counts == {
        r"\bullet": 1,
        r"\rightarrow": 1,
        r"\frac": 1,
        r"\text": 1,
    }


@pytest.mark.django_db
def test_fix_broken_latex_dry_run_and_execution() -> None:
    subject = Subject.objects.create(
        title="Biochemistry", slug="biochemistry", position=1
    )
    section = Section.objects.create(
        subject=subject,
        title="Metabolism",
        slug="metabolism",
        position=1,
    )
    topic = Topic.objects.create(
        section=section,
        title="ROS \x08ullet Title",
        description="Pathways with \r" + "ightarrow arrow",
        slug="ros-pathways",
        position=1,
    )
    block_type = ContentBlockType.objects.create(key="theory", title="Theory")
    raw_formula = (
        "$O_2^{\x08ullet-} \r"
        + "ightarrow H_2O_2 \t"
        + "ext{ and } \x0c"
        + "rac{1}{2}$"
    )
    block = ContentBlock.objects.create(
        topic=topic,
        block_type=block_type,
        position=1,
        markdown_body=raw_formula,
        caption="Caption \x08ullet",
    )
    card = Flashcard.objects.create(
        topic=topic,
        position=1,
        question="Formula \x08eta?",
        answer="Result \x08ar{x}",
    )
    quiz = Quiz.objects.create(
        topic=topic,
        title="Quiz",
        position=1,
    )
    question = QuizQuestion.objects.create(
        quiz=quiz,
        position=1,
        text="Calculate 5 \t" + "imes 10",
    )
    answer = QuizAnswer.objects.create(
        question=question,
        position=1,
        text="Answer \x0c" + "rac{a}{b}",
        is_correct=True,
    )

    # 1. DRY RUN
    out_dry = StringIO()
    call_command("fix_broken_latex", dry_run=True, stdout=out_dry)
    dry_output = out_dry.getvalue()

    assert "Model: Topic" in dry_output
    assert "Model: ContentBlock" in dry_output
    assert "Model: Flashcard" in dry_output
    assert "Model: QuizQuestion" in dry_output
    assert "Model: QuizAnswer" in dry_output
    assert "[DRY RUN] No changes were saved to the database." in dry_output

    # Verify nothing was changed in the DB
    topic.refresh_from_db()
    assert topic.title == "ROS \x08ullet Title"
    block.refresh_from_db()
    assert "\x08ullet" in block.markdown_body

    # 2. REAL EXECUTION
    out_real = StringIO()
    call_command("fix_broken_latex", stdout=out_real)
    real_output = out_real.getvalue()

    assert "Scanned:" in real_output
    assert "Affected: 5" in real_output
    assert r"\bullet: 3" in real_output
    assert r"\rightarrow: 2" in real_output
    assert r"\text: 1" in real_output
    assert r"\frac: 2" in real_output
    assert "Successfully updated 5 objects in transaction.atomic." in real_output

    # Verify changes were saved in the DB
    topic.refresh_from_db()
    assert topic.title == r"ROS \bullet Title"
    assert topic.description == r"Pathways with \rightarrow arrow"

    block.refresh_from_db()
    expected_body = r"$O_2^{\bullet-} \rightarrow H_2O_2 \text{ and } \frac{1}{2}$"
    assert block.markdown_body == expected_body
    assert block.caption == r"Caption \bullet"

    card.refresh_from_db()
    assert card.question == r"Formula \beta?"
    assert card.answer == r"Result \bar{x}"

    question.refresh_from_db()
    assert question.text == r"Calculate 5 \times 10"

    answer.refresh_from_db()
    assert answer.text == r"Answer \frac{a}{b}"

    # 3. IDEMPOTENT RE-RUN
    out_rerun = StringIO()
    call_command("fix_broken_latex", stdout=out_rerun)
    rerun_output = out_rerun.getvalue()

    assert "Affected: 0" in rerun_output
    assert "Replacements: 0" in rerun_output
    assert "No changes needed." in rerun_output
