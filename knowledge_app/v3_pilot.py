"""Opt-in versioned SDK staging pilot; not wired into production routes."""

import hashlib
import json
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from knowledge_app.agent_memory_repository import SDKRepository
from knowledge_app.graph_contracts import GraphSearch, GraphSeed
from knowledge_app.graph_service import GraphService
from knowledge_app.service import KnowledgeService, fail, owner_id
from python_foundation.errors import BusinessError, ErrorCategory
from python_foundation.security import Actor


class SourceEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: int = Field(default=1, ge=1, le=1)
    knowledge_id: UUID
    revision_id: UUID
    text: str = Field(min_length=1, max_length=200_000)
    summary: str | None = None
    sources: list[dict[str, Any]] = Field(default_factory=list)
    source_url: str | None = None
    filename: str | None = None
    edit_origin: str | None = None
    origin_machine_id: str | None = None
    origin_machine_label: str | None = None


def record_key(owner: str, knowledge_id: str, revision_id: str) -> str:
    return hashlib.sha256(
        json.dumps([owner, str(UUID(knowledge_id)), str(UUID(revision_id))]).encode()
    ).hexdigest()


def serialized(envelope: SourceEnvelope) -> str:
    return json.dumps(envelope.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class VersionedMemoryPilot:
    def __init__(self, source: KnowledgeService, sdk: SDKRepository, graph: GraphService):
        self.source, self.sdk, self.graph = source, sdk, graph

    def stage(self, actor: Actor, knowledge_id: str, revision_id: str) -> dict[str, Any]:
        owner = owner_id(actor)
        item = self.source.get(actor, knowledge_id)
        original = self.source.content(actor, knowledge_id, revision_id)
        envelope = SourceEnvelope.model_validate(
            {key: value for key, value in original.items() if key in SourceEnvelope.model_fields}
        )
        body = serialized(envelope)
        key = record_key(owner, knowledge_id, revision_id)
        metadata = {
            "schema": "knowledge-source-v3-pilot",
            "knowledge_id": str(envelope.knowledge_id),
            "revision_id": str(envelope.revision_id),
            "scope": item["scope"],
            "content_digest": digest(body),
            "embedding_profile": self.source.embedder.profile_id,
        }
        try:
            old = self.sdk.store.get("memory", key)
            if old is not None:
                if old.user_id != owner or old.content != body or old.metadata != metadata:
                    raise fail("V3_IMMUTABLE_REVISION_CONFLICT", ErrorCategory.CONFLICT)
                return {"record_id": key, "status": "READY", "reused": True}
            chunks = [piece.text for piece in self.source.embedder.split(envelope.text)]
            self.sdk.store.add(
                contents=[body],
                record_type="memory",
                record_ids=key,
                user_ids=owner,
                metadata=metadata,
                index_texts=[chunks],
            )
            self.read(actor, knowledge_id, revision_id)
            return {"record_id": key, "status": "READY", "reused": False}
        except BusinessError:
            raise
        except Exception:
            raise fail("V3_STAGE_UNCERTAIN", ErrorCategory.UNAVAILABLE) from None

    def read(self, actor: Actor, knowledge_id: str, revision_id: str) -> SourceEnvelope:
        owner = owner_id(actor)
        try:
            row = self.sdk.store.get("memory", record_key(owner, knowledge_id, revision_id))
            if row is None or row.user_id != owner:
                raise fail("V3_SOURCE_NOT_FOUND", ErrorCategory.NOT_FOUND)
            metadata = row.metadata or {}
            envelope = SourceEnvelope.model_validate_json(row.content)
            if (
                metadata.get("schema") != "knowledge-source-v3-pilot"
                or str(envelope.knowledge_id) != str(UUID(knowledge_id))
                or str(envelope.revision_id) != str(UUID(revision_id))
                or metadata.get("knowledge_id") != str(envelope.knowledge_id)
                or metadata.get("revision_id") != str(envelope.revision_id)
                or metadata.get("content_digest") != digest(row.content)
            ):
                raise fail("V3_SOURCE_INTEGRITY", ErrorCategory.CONFLICT)
            return envelope
        except BusinessError:
            raise
        except Exception:
            raise fail("V3_READ_UNAVAILABLE", ErrorCategory.UNAVAILABLE) from None

    def search(self, actor: Actor, query: str, scope: str) -> dict[str, Any]:
        owner = owner_id(actor)
        try:
            rows = self.sdk.store.search(
                query,
                k=100,
                user_id=owner,
                exact_user_match=True,
                record_types={"memory"},
                metadata_filter={
                    "schema": "knowledge-source-v3-pilot",
                    "scope": scope,
                    "embedding_profile": self.source.embedder.profile_id,
                },
                num_hops=0,
            )
            found = []
            for row, score in rows:
                metadata = row.metadata or {}
                kid, rid = metadata["knowledge_id"], metadata["revision_id"]
                if row.user_id != owner or row.id != record_key(owner, kid, rid):
                    raise fail("V3_SOURCE_INTEGRITY", ErrorCategory.CONFLICT)
                envelope = self.read(actor, kid, rid)
                current = self.source.get(actor, kid)
                if (
                    current["scope"] != scope
                    or current["lifecycle_status"] != "ACTIVE"
                    or current["revision_id"] != rid
                ):
                    continue
                found.append(
                    {
                        "record_id": row.id,
                        "knowledge_id": kid,
                        "revision_id": rid,
                        "title": current["title"],
                        "summary": envelope.summary,
                        "score": float(score),
                    }
                )
            return {
                "items": found,
                "candidate_limit_reached": len(rows) >= 100,
                "mode": "v3-pilot-vector",
                "authority": "v2-revision-lifecycle",
            }
        except BusinessError:
            raise
        except Exception:
            raise fail("V3_SEARCH_UNAVAILABLE", ErrorCategory.UNAVAILABLE) from None

    def relations(self, actor: Actor, knowledge_id: str, revision_id: str) -> dict[str, Any]:
        self.read(actor, knowledge_id, revision_id)
        current = self.source.get(actor, knowledge_id)
        return self.graph.search(
            actor,
            GraphSearch(
                seed_revisions=[GraphSeed(knowledge_id=UUID(knowledge_id), revision_id=UUID(revision_id))],
                scopes=[current["scope"]],
                depth=1,
                max_edges=20,
            ),
        )
