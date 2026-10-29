"""Bounded workflow facts tied to exact source revisions; no execution engine."""

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class WorkflowNode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_-]{0,39}$")
    label: str = Field(min_length=1, max_length=200)


class WorkflowEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str
    target: str
    relation: Literal["next", "depends_on", "assigned_to", "requires", "produces"]
    condition: str | None = Field(default=None, min_length=1, max_length=300)
    evidence: str = Field(min_length=1, max_length=800)


class WorkflowInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verified: Literal[True]
    nodes: list[WorkflowNode] = Field(min_length=2, max_length=100)
    edges: list[WorkflowEdge] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def valid_graph(self) -> "WorkflowInput":
        ids = {n.id for n in self.nodes}
        if len(ids) != len(self.nodes):
            raise ValueError("Duplicate node ID")
        seen = set()
        for edge in self.edges:
            if edge.source not in ids or edge.target not in ids:
                raise ValueError("Unknown node")
            key = (edge.source, edge.target, edge.relation, edge.condition)
            if key in seen:
                raise ValueError("Duplicate edge")
            seen.add(key)
        values = (
            [n.label for n in self.nodes]
            + [e.evidence for e in self.edges]
            + [e.condition for e in self.edges if e.condition]
        )
        if any(not v.strip() or any(ord(c) < 32 and c not in "\n\r\t" for c in v) for v in values):
            raise ValueError("Invalid literal")
        return self

    def grounded(self, content: str) -> bool:
        return all(n.label in content for n in self.nodes) and all(
            e.evidence in content and (not e.condition or e.condition in e.evidence) for e in self.edges
        )

    def canonical(self) -> str:
        value = self.model_dump()
        value["nodes"] = sorted(value["nodes"], key=lambda x: x["id"])
        value["edges"] = sorted(value["edges"], key=lambda x: json.dumps(x, sort_keys=True))
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    def digest(self) -> str:
        return hashlib.sha256(self.canonical().encode()).hexdigest()
