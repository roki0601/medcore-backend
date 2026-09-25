from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction

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

LABEL_BULLET = r"\bullet"
LABEL_RIGHTARROW = r"\rightarrow"
LABEL_TEXT = r"\text"
LABEL_FRAC = r"\frac"

# LaTeX replacements with exact control character signatures
# Format: (search_pattern, replacement, label_for_reporting)
# Ordered carefully: longer prefixes before shorter (e.g. \rightarrow before \right)
LATEX_REPLACEMENTS: tuple[tuple[str, str, str], ...] = (
    # Core requested signatures (control character + literal representation)
    ("\x08ullet", r"\bullet", LABEL_BULLET),
    (r"\x08ullet", r"\bullet", LABEL_BULLET),
    ("\r\n" + "ightarrow", r"\rightarrow", LABEL_RIGHTARROW),
    ("\r" + "ightarrow", r"\rightarrow", LABEL_RIGHTARROW),
    ("\n" + "ightarrow", r"\rightarrow", LABEL_RIGHTARROW),
    ("//rightarrow", r"\rightarrow", LABEL_RIGHTARROW),
    ("\t" + "ext", r"\text", LABEL_TEXT),
    ("\x0c" + "rac", r"\frac", LABEL_FRAC),
    (r"\x0crac", r"\frac", LABEL_FRAC),
    # Additional obvious LaTeX signatures damaged by JSON control escapes
    ("\r" + "ight", r"\right", r"\right"),
    ("\x08eta", r"\beta", r"\beta"),
    (r"\x08eta", r"\beta", r"\beta"),
    ("\x08egin", r"\begin", r"\begin"),
    (r"\x08egin", r"\begin", r"\begin"),
    ("\x08ar", r"\bar", r"\bar"),
    (r"\x08ar", r"\bar", r"\bar"),
    ("\t" + "imes", r"\times", r"\times"),
    ("\t" + "heta", r"\theta", r"\theta"),
    ("\t" + "au", r"\tau", r"\tau"),
    ("\r" + "ho", r"\rho", r"\rho"),
    ("\x0c" + "orall", r"\forall", r"\forall"),
    (r"\x0corall", r"\forall", r"\forall"),
)

# Models and fields containing educational content/markdown
TARGET_MODELS_AND_FIELDS: tuple[tuple[type[Any], tuple[str, ...]], ...] = (
    (Subject, ("title", "description")),
    (Section, ("title", "description")),
    (Topic, ("title", "description")),
    (ContentBlock, ("markdown_body", "caption")),
    (Flashcard, ("question", "answer")),
    (Quiz, ("title", "description")),
    (QuizQuestion, ("text",)),
    (QuizAnswer, ("text",)),
    (Source, ("title", "note")),
)


def fix_latex_text(value: str) -> tuple[str, dict[str, int]]:
    """Fix damaged LaTeX sequences in a single string.

    Returns the updated string and a mapping of replacement counts per label.
    Only exact signatures with control characters (\x08, \r, \t, \x0c) or their
    literal hex escape forms (\x08, \x0c) are replaced.
    """
    if not value:
        return value, {}

    counts: dict[str, int] = {}
    current = value
    for pattern, replacement, label in LATEX_REPLACEMENTS:
        count = current.count(pattern)
        if count > 0:
            current = current.replace(pattern, replacement)
            counts[label] = counts.get(label, 0) + count

    return current, counts


class Command(BaseCommand):
    help = (
        "One-off repair of damaged LaTeX sequences in educational content "
        "caused by JSON escapes."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be changed without saving modifications to DB.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        dry_run: bool = options["dry_run"]

        scanned_count = 0
        replacements_count = 0
        type_counts: dict[str, int] = {
            LABEL_BULLET: 0,
            LABEL_RIGHTARROW: 0,
            LABEL_TEXT: 0,
            LABEL_FRAC: 0,
        }

        # Store pending changes: list of (obj, model_name, field_changes_dict)
        pending_changes: list[tuple[Any, str, dict[str, str]]] = []

        for model_cls, fields in TARGET_MODELS_AND_FIELDS:
            model_name = model_cls.__name__
            queryset = model_cls.objects.all().order_by("pk")

            for obj in queryset.iterator():
                scanned_count += 1
                obj_field_updates: dict[str, str] = {}

                for field in fields:
                    original_val = getattr(obj, field) or ""
                    fixed_val, field_counts = fix_latex_text(original_val)

                    if field_counts:
                        total_field_issues = sum(field_counts.values())
                        replacements_count += total_field_issues
                        for label, c in field_counts.items():
                            type_counts[label] = type_counts.get(label, 0) + c

                        obj_field_updates[field] = fixed_val

                        if dry_run:
                            self.stdout.write(f"Model: {model_name}")
                            self.stdout.write(f"ID: {obj.pk}")
                            self.stdout.write(f"Field: {field}")
                            self.stdout.write(f"Issues: {total_field_issues}")
                            self.stdout.write(f"Before: {repr(original_val)}")
                            self.stdout.write(f"After: {repr(fixed_val)}")
                            self.stdout.write("-" * 60)

                if obj_field_updates:
                    pending_changes.append((obj, model_name, obj_field_updates))

        affected_count = len(pending_changes)

        # Output summary as required
        self.stdout.write(f"Scanned: {scanned_count}")
        self.stdout.write(f"Affected: {affected_count}")
        self.stdout.write(f"Replacements: {replacements_count}")
        self.stdout.write("")
        self.stdout.write(f"{LABEL_BULLET}: {type_counts[LABEL_BULLET]}")
        self.stdout.write(f"{LABEL_RIGHTARROW}: {type_counts[LABEL_RIGHTARROW]}")
        self.stdout.write(f"{LABEL_TEXT}: {type_counts[LABEL_TEXT]}")
        self.stdout.write(f"{LABEL_FRAC}: {type_counts[LABEL_FRAC]}")

        # Also show other types if any occurred
        extra_types = {
            k: v
            for k, v in type_counts.items()
            if k not in (LABEL_BULLET, LABEL_RIGHTARROW, LABEL_TEXT, LABEL_FRAC)
            and v > 0
        }
        if extra_types:
            self.stdout.write("")
            self.stdout.write("Additional types:")
            for k, v in sorted(extra_types.items()):
                self.stdout.write(f"{k}: {v}")

        if dry_run:
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING("[DRY RUN] No changes were saved to the database.")
            )
            return

        if affected_count == 0:
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS("No changes needed."))
            return

        # Perform atomic commit
        with transaction.atomic():
            for obj, _model_name, updates in pending_changes:
                for field_name, new_val in updates.items():
                    setattr(obj, field_name, new_val)
                obj.save(update_fields=list(updates.keys()))

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully updated {affected_count} objects in transaction.atomic."
            )
        )
