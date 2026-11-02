from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EvidenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    memory_id: str = Field(min_length=1, max_length=128)
    knowledge_id: str = Field(min_length=1, max_length=36)
    revision_id: str = Field(min_length=1, max_length=36)
    quote: str = Field(min_length=1, max_length=4000)
    reason: str = Field(min_length=1, max_length=1000)


class MemoryLink(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    source_id: str = Field(min_length=1, max_length=128)
    target_id: str = Field(min_length=1, max_length=128)
    relation: Literal["supports", "contradicts", "supersedes", "refines", "duplicates"]
    reason: str = Field(min_length=1, max_length=1000)


class MemoryGraph(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    memory_id: str = Field(min_length=1, max_length=128)
    depth: int = Field(default=1, ge=1, le=3)
    max_edges: int = Field(default=30, ge=1, le=100)
    scopes: list[str] | None = Field(default=None, min_length=1, max_length=10)
