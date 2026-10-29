"""Public contracts for shared, evidence-backed, bitemporal assertions."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from knowledge_app.contracts import normalize_scope


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EntityInput(Strict):
    scope: str = "global"
    identity_key: str = Field(min_length=1, max_length=200)
    label: str = Field(min_length=1, max_length=200)
    kind: str = Field(default="concept", min_length=1, max_length=40)
    aliases: list[str] = Field(default_factory=list, max_length=20)

    _scope = field_validator("scope")(normalize_scope)

    @field_validator("identity_key", "label", "kind")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip() or any(ord(c) < 32 for c in value):
            raise ValueError("Invalid entity text")
        return value.strip()

    @field_validator("aliases")
    @classmethod
    def valid_aliases(cls, values: list[str]) -> list[str]:
        if any(not v.strip() or len(v) > 200 for v in values):
            raise ValueError("Invalid aliases")
        return list(dict.fromkeys(v.strip() for v in values))


class EvidenceInput(Strict):
    knowledge_id: UUID
    revision_id: UUID
    quote: str = Field(min_length=1, max_length=800)


class TemporalBasis(Strict):
    text: str = Field(min_length=1, max_length=800)
    user_asserted: bool = False


class AssertionInput(Strict):
    scope: str = "global"
    subject_id: UUID
    predicate: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    object_id: UUID | None = None
    literal: str | None = Field(default=None, min_length=1, max_length=800)
    condition: str | None = Field(default=None, min_length=1, max_length=300)
    temporal_kind: Literal["UNKNOWN", "TIMELESS", "INTERVAL"] = "UNKNOWN"
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    temporal_basis: TemporalBasis | None = None
    evidence: list[EvidenceInput] = Field(min_length=1, max_length=50)
    verified: Literal[True]
    status: Literal["ACTIVE", "RETRACTED"] = "ACTIVE"
    change_note: str | None = Field(default=None, max_length=500)

    _scope = field_validator("scope")(normalize_scope)

    @model_validator(mode="after")
    def valid_fact(self) -> "AssertionInput":
        if (self.object_id is None) == (self.literal is None):
            raise ValueError("Provide one object_id or literal")
        for value in (self.valid_from, self.valid_to):
            if value and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError("Timezone is required")
        if self.temporal_kind == "INTERVAL":
            if self.valid_from is None or self.temporal_basis is None:
                raise ValueError("An interval needs its start and confirmed basis")
            if self.valid_to and self.valid_to <= self.valid_from:
                raise ValueError("End must follow start")
        elif self.valid_from or self.valid_to:
            raise ValueError("Dates require INTERVAL")
        if self.temporal_kind == "TIMELESS" and self.temporal_basis is None:
            raise ValueError("Timelessness needs a confirmed basis")
        return self


class AssertionRevision(AssertionInput):
    expected_version_id: UUID


class GraphSeed(Strict):
    knowledge_id: UUID
    revision_id: UUID


class GraphSearch(Strict):
    query: str = Field(default="", max_length=2000)
    scopes: list[str] | None = Field(default=None, min_length=1, max_length=10)
    entity_ids: list[UUID] = Field(default_factory=list, max_length=20)
    knowledge_id: UUID | None = None
    seed_revisions: list[GraphSeed] = Field(default_factory=list, max_length=10)
    valid_at: datetime | None = None
    known_at: datetime | None = None
    include_undated: bool = False
    depth: int = Field(default=1, ge=0, le=3)
    max_edges: int = Field(default=40, ge=1, le=100)
    direction: Literal["both", "outgoing", "incoming"] = "both"
    predicates: list[str] = Field(default_factory=list, max_length=20)
    include_entity_matches: bool = False

    @field_validator("predicates")
    @classmethod
    def valid_predicates(cls, values: list[str]) -> list[str]:
        import re

        if any(not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", v) for v in values):
            raise ValueError("Invalid predicate")
        return list(dict.fromkeys(values))

    @model_validator(mode="after")
    def validate_seeds(self) -> "GraphSearch":
        if self.knowledge_id and self.seed_revisions:
            raise ValueError("Choose knowledge_id or seed_revisions")
        if (
            self.seed_revisions
            and (self.query.strip() or self.entity_ids)
            and not self.include_entity_matches
        ):
            raise ValueError("Revision seeds cannot be mixed with entity seeds")
        return self

    @field_validator("scopes")
    @classmethod
    def scopes_valid(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else list(dict.fromkeys(normalize_scope(v) for v in value))

    @field_validator("valid_at", "known_at")
    @classmethod
    def aware(cls, value: datetime | None) -> datetime | None:
        if value and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("Timezone is required")
        return value
