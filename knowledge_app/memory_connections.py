"""Source-backed cross-store references and bounded SDK graph traversal."""

from collections import deque
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from knowledge_app.agent_memory_service import TYPES, AgentMemoryService, stable_id
from knowledge_app.contracts import Search
from knowledge_app.memory_connection_contracts import EvidenceInput, MemoryGraph, MemoryLink
from knowledge_app.memory_evidence_models import MemoryEvidence
from knowledge_app.models import Item, Revision
from knowledge_app.service import KnowledgeService, fail, owner_id
from python_foundation.database import SqlAlchemyUnitOfWork
from python_foundation.errors import BusinessError, ErrorCategory
from python_foundation.security import Actor


class MemoryConnections:
    def __init__(
        self, memories: AgentMemoryService, knowledge: KnowledgeService, factory: sessionmaker[Session]
    ):
        self.memories, self.knowledge, self.factory = memories, knowledge, factory

    def record(self, owner: str, memory_id: str) -> tuple[str, Any]:
        self.memories.check()
        for typ in TYPES:
            row = self.memories.repo.store.get(typ, memory_id)
            if row is not None and row.user_id == owner:
                return typ, row
        raise fail("MEMORY_NOT_FOUND", ErrorCategory.NOT_FOUND)

    @staticmethod
    def node(typ: str, row: Any) -> dict[str, Any]:
        m = row.metadata or {}
        return dict(
            id=row.id,
            title=m.get("title") or (row.content or "")[:120],
            text=row.content or "",
            memory_type=typ,
            status=str(getattr(row.status, "value", row.status)),
            scope=m.get("scope", "global"),
        )

    def prepare(self, memory_id: str, actor: Actor) -> dict[str, Any]:
        try:
            _, row = self.record(owner_id(actor), memory_id)
            scope = (row.metadata or {}).get("scope", "global")
            result = self.knowledge.search(
                actor,
                Search(
                    query=(row.content or "")[:2000], scopes=list(dict.fromkeys(["global", scope])), top_k=5
                ),
            )
            return {
                "memory_id": memory_id,
                "items": result["items"],
                "writes_performed": False,
                "next_step": "Read exact candidate revision. Link only when quote and conditions support the memory. Scores are not evidence.",
            }
        except BusinessError:
            raise
        except Exception:
            raise fail("MEMORY_CONNECTION_UNAVAILABLE", ErrorCategory.UNAVAILABLE) from None

    def link_evidence(self, command: EvidenceInput, actor: Actor) -> dict[str, Any]:
        owner = owner_id(actor)
        try:
            self.record(owner, command.memory_id)
            link_id = stable_id(owner, "evidence", command.model_dump_json())

            # Same owner lock as SDK writes. Source item lock serializes active revision changes.
            def write() -> dict[str, Any]:
                with SqlAlchemyUnitOfWork(self.factory) as uow:
                    item = uow.session.scalar(
                        select(Item)
                        .where(Item.id == command.knowledge_id, Item.owner_id == owner)
                        .with_for_update()
                    )
                    revision = uow.session.scalar(
                        select(Revision).where(
                            Revision.id == command.revision_id,
                            Revision.owner_id == owner,
                            Revision.item_id == command.knowledge_id,
                        )
                    )
                    if item is None or revision is None:
                        raise fail("MEMORY_SOURCE_NOT_FOUND", ErrorCategory.NOT_FOUND)
                    existing = uow.session.get(MemoryEvidence, link_id)
                    if existing:
                        return {
                            "id": link_id,
                            "reused": True,
                            "status": self.currentness(item, revision, existing),
                        }
                    if item.lifecycle_status != "ACTIVE" or item.active_revision_id != revision.id:
                        raise fail("MEMORY_SOURCE_NOT_CURRENT", ErrorCategory.CONFLICT)
                    if not revision.content_text or command.quote not in revision.content_text:
                        raise fail("MEMORY_QUOTE_MISMATCH")
                    uow.session.add(MemoryEvidence(id=link_id, owner_id=owner, **command.model_dump()))
                    return {"id": link_id, "reused": False, "status": "CURRENT"}

            return self.memories.mutate(owner, write)
        except BusinessError:
            raise
        except Exception:
            raise fail("MEMORY_CONNECTION_WRITE_UNCERTAIN", ErrorCategory.UNAVAILABLE) from None

    @staticmethod
    def currentness(item: Item, revision: Revision, link: MemoryEvidence) -> str:
        return (
            "CURRENT"
            if item.lifecycle_status == "ACTIVE"
            and item.active_revision_id == link.revision_id
            and revision.content_text
            and link.quote in revision.content_text
            else "REVIEW_REQUIRED"
        )

    def references(
        self,
        actor: Actor,
        *,
        memory_id: str | None = None,
        knowledge_id: str | None = None,
        offset: int = 0,
        limit: int = 20,
        scopes: list[str] | None = None,
    ) -> dict[str, Any]:
        owner = owner_id(actor)
        if (memory_id is None) == (knowledge_id is None):
            raise fail("ONE_REFERENCE_TARGET_REQUIRED")
        try:
            if memory_id:
                self.record(owner, memory_id)
            with SqlAlchemyUnitOfWork(self.factory, read_only=True) as uow:
                if (
                    knowledge_id
                    and uow.session.scalar(
                        select(Item.id).where(Item.id == knowledge_id, Item.owner_id == owner)
                    )
                    is None
                ):
                    raise fail("KNOWLEDGE_NOT_FOUND", ErrorCategory.NOT_FOUND)
                stmt = (
                    select(MemoryEvidence, Item, Revision)
                    .join(
                        Item,
                        (Item.id == MemoryEvidence.knowledge_id) & (Item.owner_id == MemoryEvidence.owner_id),
                    )
                    .join(
                        Revision,
                        (Revision.id == MemoryEvidence.revision_id)
                        & (Revision.owner_id == MemoryEvidence.owner_id),
                    )
                    .where(MemoryEvidence.owner_id == owner)
                )
                stmt = (
                    stmt.where(MemoryEvidence.memory_id == memory_id)
                    if memory_id
                    else stmt.where(MemoryEvidence.knowledge_id == knowledge_id)
                )
                if scopes:
                    stmt = stmt.where(Item.scope.in_(scopes))
                rows = uow.session.execute(
                    stmt.order_by(MemoryEvidence.created_at.desc(), MemoryEvidence.id)
                    .offset(offset)
                    .limit(limit + 1)
                ).all()
                items = []
                for link, item, revision in rows[:limit]:
                    try:
                        typ, memory = self.record(owner, link.memory_id)
                    except BusinessError as exc:
                        if exc.error.code == "MEMORY_NOT_FOUND":
                            continue
                        raise
                    items.append(
                        dict(
                            id=link.id,
                            memory=self.node(typ, memory),
                            knowledge_id=item.id,
                            title=item.title,
                            revision_id=revision.id,
                            active_revision_id=item.active_revision_id,
                            status=self.currentness(item, revision, link),
                            quote=link.quote,
                            reason=link.reason,
                            scope=item.scope,
                            created_at=link.created_at.isoformat(),
                        )
                    )
                return {"items": items, "next_offset": offset + limit if len(rows) > limit else None}
        except BusinessError:
            raise
        except Exception:
            raise fail("MEMORY_CONNECTION_UNAVAILABLE", ErrorCategory.UNAVAILABLE) from None

    def link(self, command: MemoryLink, actor: Actor) -> dict[str, Any]:
        owner = owner_id(actor)
        if command.source_id == command.target_id:
            raise fail("MEMORY_SELF_LINK")
        try:

            def write() -> dict[str, Any]:
                source_type, _ = self.record(owner, command.source_id)
                target_type, _ = self.record(owner, command.target_id)
                rid = stable_id(
                    owner, "memory_relation", f"{command.source_id}:{command.relation}:{command.target_id}"
                )
                existing = self.memories.repo.store.get_relation(relation_id=rid)
                if existing is not None:
                    if (existing.metadata or {}).get("reason") != command.reason:
                        raise fail("MEMORY_RELATION_CONFLICT", ErrorCategory.CONFLICT)
                    return {"id": rid, "reused": True}
                self.memories.repo.client.link_records(
                    command.source_id,
                    source_type,
                    command.target_id,
                    target_type,
                    command.relation,
                    relation_id=rid,
                    metadata={"owner_id": owner, "reason": command.reason},
                )
                return {"id": rid, "reused": False}

            return self.memories.mutate(owner, write)
        except BusinessError:
            raise
        except Exception:
            raise fail("MEMORY_RELATION_WRITE_UNCERTAIN", ErrorCategory.UNAVAILABLE) from None

    def graph(self, command: MemoryGraph, actor: Actor) -> dict[str, Any]:
        owner = owner_id(actor)
        try:
            typ, seed = self.record(owner, command.memory_id)
            if command.scopes and (seed.metadata or {}).get("scope", "global") not in command.scopes:
                raise fail("MEMORY_NOT_FOUND", ErrorCategory.NOT_FOUND)
            nodes = {seed.id: self.node(typ, seed)}
            edges: dict[str, Any] = {}
            queue = deque([(seed.id, 0)])
            visited = set()
            truncated = False
            while queue:
                current, depth = queue.popleft()
                if current in visited or depth >= command.depth:
                    continue
                visited.add(current)
                for direction in ("source_record_id", "target_record_id"):
                    relations = self.memories.repo.store.list_relations(
                        **{direction: current},
                        metadata_filter={"owner_id": owner},
                        limit=command.max_edges + 1,
                    )
                    if len(relations) > command.max_edges:
                        truncated = True
                    for rel in relations:
                        if rel.id in edges:
                            continue
                        if len(edges) >= command.max_edges:
                            truncated = True
                            break
                        endpoints: list[dict[str, Any]] = []
                        for endpoint in (rel.source_record_id, rel.target_record_id):
                            try:
                                t, r = self.record(owner, endpoint)
                            except BusinessError as exc:
                                if exc.error.code == "MEMORY_NOT_FOUND":
                                    endpoints = []
                                    break
                                raise
                            n = self.node(t, r)
                            if command.scopes and n["scope"] not in command.scopes:
                                endpoints = []
                                break
                            endpoints.append(n)
                        if len(endpoints) != 2:
                            continue
                        for n in endpoints:
                            nodes[n["id"]] = n
                            if n["id"] not in visited:
                                queue.append((n["id"], depth + 1))
                        edges[rel.id] = dict(
                            id=rel.id,
                            source=rel.source_record_id,
                            target=rel.target_record_id,
                            relation=rel.relation_type,
                            reason=(rel.metadata or {}).get("reason", ""),
                        )
            return dict(
                nodes=list(nodes.values()),
                edges=list(edges.values()),
                truncated=truncated,
                depth=command.depth,
                max_edges=command.max_edges,
            )
        except BusinessError:
            raise
        except Exception:
            raise fail("MEMORY_GRAPH_UNAVAILABLE", ErrorCategory.UNAVAILABLE) from None
