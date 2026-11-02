"""Agent-authored clarification, never established graph facts."""

from typing import Literal, Self
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from knowledge_app.graph_contracts import Strict


class CaptureQuestion(Strict):
    key: str = Field(min_length=1, max_length=60, pattern=r"^[a-zA-Z0-9_-]+$")
    question: str = Field(min_length=1, max_length=1000)
    reason: str = Field(min_length=1, max_length=1000)
    quote: str = Field(min_length=1, max_length=2000)
    options: list[str] = Field(default_factory=list, max_length=3)

    @field_validator("question", "reason", "quote")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Nonblank text required")
        return value


class CaptureDraft(Strict):
    revision_id: UUID
    expected_version: int = Field(ge=0)
    summary: str = Field(min_length=1, max_length=3000)
    hypotheses: list[str] = Field(default_factory=list, max_length=10)
    questions: list[CaptureQuestion] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def bounded(self) -> Self:
        if not self.summary.strip() or any(not x.strip() or len(x) > 1000 for x in self.hypotheses):
            raise ValueError("Invalid draft text")
        if len({q.key for q in self.questions}) != len(self.questions):
            raise ValueError("Duplicate question key")
        if any(not x.strip() or len(x) > 500 for q in self.questions for x in q.options):
            raise ValueError("Invalid option")
        return self


class CaptureAnswer(Strict):
    revision_id: UUID
    expected_version: int = Field(ge=1)
    question_key: str = Field(min_length=1, max_length=60)
    disposition: Literal["answered", "deferred", "not_applicable"] = "answered"
    text: str = Field(min_length=1, max_length=3000)

    @field_validator("text")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Answer or reason required")
        return value
