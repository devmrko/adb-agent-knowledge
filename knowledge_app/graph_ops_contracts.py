from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from knowledge_app.contracts import normalize_scope
from knowledge_app.graph_contracts import EvidenceInput, GraphSearch, Strict


class ReviewUpdate(Strict):
    revision_id: UUID
    expected_version: int = Field(ge=0)
    status: Literal["REVIEWING", "COMPLETE", "FAILED"]
    outcome: Literal["RELATIONS", "NONE", "UNRESOLVED"] | None = None
    note: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def outcome_matches(self) -> "ReviewUpdate":
        if not self.note.strip():
            raise ValueError("Review note required")
        if self.status == "COMPLETE" and self.outcome not in {"RELATIONS", "NONE"}:
            raise ValueError("Complete review requires RELATIONS or NONE")
        if self.status != "COMPLETE" and self.outcome not in {None, "UNRESOLVED"}:
            raise ValueError("Incomplete review cannot declare completion")
        return self


class IdentityBind(Strict):
    entity_id: UUID
    kind: Literal["alias", "external"]
    namespace: str = Field(min_length=1, max_length=40, pattern=r"^[a-z][a-z0-9_-]*$")
    value: str = Field(min_length=1, max_length=500)
    expected_version: int = Field(default=0, ge=0)
    status: Literal["ACTIVE", "RETRACTED"] = "ACTIVE"
    evidence: EvidenceInput
    note: str = Field(min_length=1, max_length=1000)

    @field_validator("value", "note")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Nonblank value required")
        return value.strip()


class IdentityResolve(Strict):
    query: str = Field(min_length=1, max_length=500)
    scopes: list[str] = Field(min_length=1, max_length=10)
    namespace: str | None = Field(default=None, max_length=40)

    @field_validator("scopes")
    @classmethod
    def scope_values(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(normalize_scope(v) for v in values))


class GraphExplore(Strict):
    intent: Literal["evidence", "dependencies"]
    search: GraphSearch
