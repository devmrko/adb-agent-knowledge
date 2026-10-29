"""Versioned extraction contract: model output is untrusted candidate data."""

from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from knowledge_app.graph_contracts import Strict
from knowledge_app.settings import ROOT

SCHEMA_VERSION = "operations-v3"
EntityKind = Literal[
    "project",
    "project_area",
    "component",
    "template",
    "service",
    "machine",
    "resource",
    "document",
    "task",
    "incident",
    "action",
    "decision",
]
KINDS = {
    "project",
    "project_area",
    "component",
    "template",
    "service",
    "machine",
    "resource",
    "document",
    "task",
    "incident",
    "action",
    "decision",
}
PATTERNS: dict[str, tuple[set[str], set[str]]] = {
    "uses": (
        {"project", "component", "service", "task", "action"},
        {"service", "resource", "machine", "document"},
    ),
    "depends_on": (
        {"project", "component", "service", "task", "resource"},
        {"project", "component", "service", "task", "resource", "machine"},
    ),
    "deployed_on": ({"service"}, {"machine", "resource"}),
    "part_of": ({"project_area", "component", "service"}, {"project", "component", "service"}),
    "created_from": ({"project", "component", "service"}, {"template", "project"}),
    "affects": ({"incident", "action", "decision"}, {"project", "service", "machine", "resource", "task"}),
    "addresses": ({"action", "decision", "task"}, {"incident"}),
    "documents": ({"document"}, KINDS),
    "precedes": ({"task", "action"}, {"task", "action"}),
}


class AutoGraphSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore", env_prefix="GRAPH_AUTO_")
    enabled: bool = False
    url: str = "http://127.0.0.1:1234/v1"
    model: str = ""
    api_key: SecretStr = Field(
        default=SecretStr(""), validation_alias=AliasChoices("GRAPH_AUTO_API_KEY", "OPENROUTER_API_KEY")
    )
    allow_remote: bool = False
    structured_output: bool = False
    timeout_seconds: float = Field(default=90, ge=1, le=120)
    reasoning_effort: Literal["none", "low", "medium", "high"] | None = None
    max_chars: int = Field(default=24000, ge=1000, le=100000)
    # REVIEW is deliberate: identity suggestions are not proof of identity.
    policy: Literal["review", "auto_existing", "auto_verified"] = "review"

    @model_validator(mode="after")
    def endpoint(self) -> "AutoGraphSettings":
        p = urlsplit(self.url)
        local = p.hostname in {"localhost", "127.0.0.1", "::1"}
        if p.username or p.password or p.query or p.fragment or not p.hostname:
            raise ValueError("Invalid graph extraction endpoint")
        if not ((local and p.scheme in {"http", "https"}) or (self.allow_remote and p.scheme == "https")):
            raise ValueError("Remote graph extraction requires explicit opt-in and HTTPS")
        if self.enabled and not self.model.strip():
            raise ValueError("GRAPH_AUTO_MODEL is required when enabled")
        return self


class ExtractedEntity(Strict):
    key: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=200)
    kind: EntityKind
    mention: str = Field(min_length=1, max_length=300)
    existing_id: UUID | None = None

    @field_validator("key", "label", "mention")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Nonblank entity fields required")
        return value


class ExtractedRelation(Strict):
    subject: str = Field(
        min_length=1, max_length=80, description="Exact key of a declared entity, not its label"
    )
    predicate: str = Field(min_length=1, max_length=40)
    object: str = Field(
        min_length=1, max_length=80, description="Exact key of a declared entity, not its label"
    )
    quote: str = Field(min_length=1, max_length=800)
    condition: str | None = Field(default=None, min_length=1, max_length=300)


class Extraction(Strict):
    rejected_relations: int = Field(default=0, ge=0, le=100)
    entities: list[ExtractedEntity] = Field(max_length=60)
    relations: list[ExtractedRelation] = Field(max_length=100)

    @model_validator(mode="after")
    def graph_shape(self) -> "Extraction":
        nodes = {e.key: e for e in self.entities}
        if len(nodes) != len(self.entities):
            raise ValueError("Duplicate entity keys")
        for r in self.relations:
            if r.subject not in nodes or r.object not in nodes or r.subject == r.object:
                raise ValueError("Invalid endpoints")
            types = PATTERNS.get(r.predicate)
            if types is None or nodes[r.subject].kind not in types[0] or nodes[r.object].kind not in types[1]:
                raise ValueError("Relation does not match operations-v3")
        return self


class EntityResolution(Strict):
    existing_id: UUID | None = None
    identity_key: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def one_identity(self) -> "EntityResolution":
        if (self.existing_id is None) == (self.identity_key is None):
            raise ValueError("Select existing ID or a confirmed new identity key")
        if self.identity_key and not self.identity_key.strip():
            raise ValueError("Nonblank identity required")
        return self


class ReviewCandidate(Strict):
    decision: Literal["approve", "reject"]
    note: str = Field(min_length=1, max_length=1000)
    subject: EntityResolution | None = None
    object: EntityResolution | None = None

    @model_validator(mode="after")
    def checked(self) -> "ReviewCandidate":
        if not self.note.strip():
            raise ValueError("Review note required")
        if self.decision == "approve" and (self.subject is None or self.object is None):
            raise ValueError("Explicit endpoint identity confirmation required")
        return self
