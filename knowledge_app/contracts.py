import re
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MemoryKind = Literal["DOCUMENT", "DECISION", "PREFERENCE", "FACT", "PROCEDURE", "EPISODE"]
SCOPE = re.compile(r"global|(?:project|thread|agent):[a-z0-9][a-z0-9._-]{0,99}")


def normalize_scope(value: str) -> str:
    value = value.strip().lower()
    if not SCOPE.fullmatch(value):
        raise ValueError("Scope must be 'global' or 'project/thread/agent:<key>'")
    return value


class SourceLocation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["local_file", "url", "git", "object", "reference"]
    location: str = Field(min_length=1, max_length=2000)
    machine_id: str | None = Field(default=None, min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9._-]+$")
    version: str | None = Field(default=None, max_length=200)
    locator: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def validate_location(self) -> "SourceLocation":
        if not self.location.strip() or any(ord(c) < 32 for c in self.location):
            raise ValueError("Invalid source location")
        if self.kind == "local_file" and not self.machine_id:
            raise ValueError("Local files require the source machine_id")
        if "://" in self.location:
            parsed = urlsplit(self.location)
            if parsed.username or parsed.password or parsed.query:
                raise ValueError("Source locations must not contain credentials or query strings")
        return self


class Provenance(BaseModel):
    edit_origin: Literal["HUMAN", "AGENT", "API", "UNKNOWN"] = "API"
    model_config = ConfigDict(extra="forbid")
    origin_machine_id: str | None = Field(
        default=None, min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9._-]+$"
    )
    origin_machine_label: str | None = Field(default=None, min_length=1, max_length=120)
    sources: list[SourceLocation] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def label_needs_id(self) -> "Provenance":
        if self.origin_machine_label and not self.origin_machine_id:
            raise ValueError("Machine label requires machine ID")
        return self


class SummaryInput(Provenance):
    summary: str | None = Field(default=None, min_length=1, max_length=2000)

    @field_validator("summary")
    @classmethod
    def summary_nonblank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Blank summary")
        return value.strip() if value else None


class CreateKnowledge(SummaryInput):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=300)
    knowledge_type: Literal["NOTE", "FAQ", "MANUAL", "MEETING", "TROUBLESHOOTING", "OTHER"] = "NOTE"
    memory_kind: MemoryKind = "DOCUMENT"
    scope: str = Field(default="global", max_length=108)
    category: str | None = Field(default=None, max_length=120)
    tags: list[str] = Field(default_factory=list, max_length=30)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=100)
    text: str | None = Field(default=None, max_length=200_000)
    url: str | None = Field(default=None, max_length=2000)

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Blank title")
        return value.strip()

    @field_validator("scope")
    @classmethod
    def valid_scope(cls, value: str) -> str:
        return normalize_scope(value)

    @field_validator("tags")
    @classmethod
    def valid_tags(cls, values: list[str]) -> list[str]:
        if any(not v.strip() or len(v) > 80 for v in values):
            raise ValueError("Invalid tag")
        return list(dict.fromkeys(v.strip() for v in values))


class ReviseKnowledge(SummaryInput):
    expected_revision_id: UUID
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=200_000)
    change_note: str | None = Field(default=None, max_length=500)


class RetireKnowledge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=500)
    superseded_by: UUID | None = None


class RestoreKnowledge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str | None = Field(default=None, max_length=500)


class Search(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)
    category: str | None = None
    knowledge_type: str | None = None
    memory_kinds: list[MemoryKind] | None = Field(default=None, min_length=1, max_length=6)
    scopes: list[str] | None = Field(default=None, min_length=1, max_length=10)
    include_graph: bool = False
    has_relations: bool = False
    include_retired: bool = False
    min_similarity: float | None = Field(default=None, ge=0, le=1)

    @field_validator("query")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Blank query")
        return value.strip()

    @field_validator("scopes")
    @classmethod
    def valid_scopes(cls, values: list[str] | None) -> list[str] | None:
        return None if values is None else list(dict.fromkeys(normalize_scope(v) for v in values))


class ContextRequest(Search):
    max_chars: int = Field(default=6000, ge=500, le=20000)
