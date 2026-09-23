from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SUPPORTED_BLOCK_TYPES = ("markdown", "callout")


class ImportBlock(BaseModel):
    model_config = ConfigDict(extra="ignore")

    block_type: str = Field(..., description="Block type: markdown or callout")
    caption: str = Field(default="", description="Optional caption")
    markdown_body: str = Field(..., description="Markdown content body")

    @field_validator("block_type")
    @classmethod
    def validate_block_type(cls, value: str) -> str:
        v = (value or "").strip().lower()
        if v not in SUPPORTED_BLOCK_TYPES:
            types_str = ", ".join(SUPPORTED_BLOCK_TYPES)
            raise ValueError(
                f'Unknown block_type "{value}". Supported types: {types_str}.'
            )
        return v

    @field_validator("markdown_body")
    @classmethod
    def validate_markdown_body_non_blank(cls, value: str) -> str:
        if not (value or "").strip():
            raise ValueError("Markdown body cannot be blank.")
        return value


class ImportContent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str = Field(default="")
    summary: str | None = Field(default=None)
    exam_focus: list[str] | None = Field(default=None)
    blocks: list[ImportBlock] = Field(default_factory=list)


class ImportFlashcard(BaseModel):
    model_config = ConfigDict(extra="ignore")

    question: str = Field(..., description="Flashcard question text")
    answer: str = Field(..., description="Flashcard answer text")

    @field_validator("question")
    @classmethod
    def validate_question_non_blank(cls, value: str) -> str:
        if not (value or "").strip():
            raise ValueError("Flashcard question cannot be blank.")
        return value

    @field_validator("answer")
    @classmethod
    def validate_answer_non_blank(cls, value: str) -> str:
        if not (value or "").strip():
            raise ValueError("Flashcard answer cannot be blank.")
        return value


class ImportQuizAnswer(BaseModel):
    model_config = ConfigDict(extra="ignore")

    text: str = Field(..., description="Answer text")
    is_correct: bool = Field(default=False)

    @field_validator("text")
    @classmethod
    def validate_text_non_blank(cls, value: str) -> str:
        if not (value or "").strip():
            raise ValueError("Answer text cannot be blank.")
        return value


class ImportQuizQuestion(BaseModel):
    model_config = ConfigDict(extra="ignore")

    text: str = Field(..., description="Question text")
    answers: list[ImportQuizAnswer] = Field(default_factory=list)

    @field_validator("text")
    @classmethod
    def validate_text_non_blank(cls, value: str) -> str:
        if not (value or "").strip():
            raise ValueError("Question text cannot be blank.")
        return value

    @model_validator(mode="after")
    def validate_answers(self) -> ImportQuizQuestion:
        if len(self.answers) < 2:
            raise ValueError("Question must contain at least 2 answers.")

        correct_count = sum(1 for a in self.answers if a.is_correct)
        if correct_count != 1:
            raise ValueError(
                f"Question must contain exactly one correct answer "
                f"(found {correct_count})."
            )

        seen_answers: set[str] = set()
        for ans in self.answers:
            normalized = ans.text.strip().casefold()
            if normalized in seen_answers:
                raise ValueError(f"Duplicate answer text: '{ans.text}'.")
            seen_answers.add(normalized)

        return self


class ImportQuiz(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str = Field(default="")
    description: str = Field(default="")
    questions: list[ImportQuizQuestion] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_quiz(self) -> ImportQuiz:
        if len(self.questions) < 1:
            raise ValueError("Quiz must contain at least 1 question.")
        return self


class ImportStudyDocument(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: int = Field(...)
    topic: str = Field(...)
    content: ImportContent = Field(default_factory=ImportContent)
    flashcards: list[ImportFlashcard] = Field(default_factory=list)
    quiz: ImportQuiz = Field(...)
    generation: dict[str, Any] | None = Field(default=None)
    external_id: str | None = Field(default=None)

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: int) -> int:
        if value != 1:
            raise ValueError(
                f"schema_version {value} is not supported. "
                "Only schema_version=1 is supported."
            )
        return value

    @field_validator("topic")
    @classmethod
    def validate_topic_non_blank(cls, value: str) -> str:
        if not (value or "").strip():
            raise ValueError("Topic title cannot be blank.")
        return value


def format_validation_error(exc_errors: list[dict[str, Any]]) -> str:
    """Format Pydantic errors into human-readable messages."""
    messages = []
    for err in exc_errors:
        loc = err.get("loc", ())
        raw_msg = err.get("msg", "")
        # Strip ValueError prefix if present
        if raw_msg.startswith("Value error, "):
            msg = raw_msg[len("Value error, ") :]
        else:
            msg = raw_msg

        # Format location nicely
        if loc and loc[0] == "schema_version":
            messages.append(msg)
        elif len(loc) >= 3 and loc[0] == "content" and loc[1] == "blocks":
            block_num = loc[2] + 1
            if len(loc) >= 4 and loc[3] == "block_type":
                messages.append(f"Block #{block_num} has {msg}")
            else:
                messages.append(f"Block #{block_num}: {msg}")
        elif len(loc) >= 3 and loc[0] == "quiz" and loc[1] == "questions":
            q_num = loc[2] + 1
            if len(loc) >= 5 and loc[3] == "answers":
                ans_num = loc[4] + 1
                messages.append(f"Question #{q_num}, Answer #{ans_num}: {msg}")
            else:
                messages.append(f"Question #{q_num}: {msg}")
        elif len(loc) >= 2 and loc[0] == "flashcards":
            fc_num = loc[1] + 1
            field_name = loc[2] if len(loc) >= 3 else "field"
            messages.append(f"Flashcard #{fc_num} ({field_name}): {msg}")
        elif loc and loc[0] == "quiz":
            messages.append(f"Quiz: {msg}")
        elif loc and loc[0] == "topic":
            messages.append(f"Topic: {msg}")
        else:
            loc_str = " -> ".join(str(item) for item in loc)
            messages.append(f"{loc_str}: {msg}" if loc_str else msg)

    return "\n".join(messages)
