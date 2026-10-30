import json
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from knowledge_app.audit_context import audited_uow
from knowledge_app.graph_contracts import GraphSearch
from knowledge_app.graph_ops_contracts import GraphExplore, IdentityBind, IdentityResolve, ReviewUpdate
from knowledge_app.graph_ops_models import GraphIdentity
from knowledge_app.graph_ops_repository import GraphOpsRepository, snapshot
from knowledge_app.graph_repository import GraphRepository
from knowledge_app.graph_service import GraphService, digest, entity_view
from knowledge_app.models import now, uid
from knowledge_app.service import fail, owner_id
from knowledge_app.settings import Settings
from python_foundation.database import SqlAlchemyUnitOfWork
from python_foundation.errors import ErrorCategory
from python_foundation.security import Actor


class GraphOpsService:
    def __init__(self, factory: sessionmaker[Session], settings: Settings):
        self.factory, self.settings = factory, settings

    def enabled(self) -> None:
        if not self.settings.workflow_rdf_enabled:
            raise fail("WORKFLOW_DISABLED", ErrorCategory.UNAVAILABLE)

    def backlog(self, actor: Actor, scopes: list[str] | None, offset: int, limit: int) -> dict[str, Any]:
        self.enabled()
        with SqlAlchemyUnitOfWork(self.factory, read_only=True) as uow:
            rows = GraphOpsRepository(uow.session).backlog(owner_id(actor), scopes, offset, limit)
            return {
                "items": [
                    dict(
                        knowledge_id=item.id,
                        revision_id=item.active_revision_id,
                        title=item.title,
                        scope=item.scope,
                        review=snapshot(row)
                        if row
                        else {
                            "id": None,
                            "version": 0,
                            "status": "PENDING",
                            "outcome": None,
                            "note": "Existing source; review not yet started",
                        },
                    )
                    for item, row in rows[:limit]
                ],
                "next_offset": offset + limit if len(rows) > limit else None,
            }

    def review(self, actor: Actor, item_id: str, command: ReviewUpdate) -> dict[str, Any]:
        self.enabled()
        owner = owner_id(actor)
        try:
            with audited_uow(self.factory, actor, "GRAPH_REVIEW", command) as uow:
                repo = GraphOpsRepository(uow.session)
                source = repo.source(owner, item_id, str(command.revision_id))
                if source is None:
                    raise fail("KNOWLEDGE_NOT_FOUND", ErrorCategory.NOT_FOUND)
                item, revision = source
                if item.lifecycle_status != "ACTIVE" or item.active_revision_id != revision.id:
                    raise fail("GRAPH_SOURCE_STALE", ErrorCategory.CONFLICT)
                row = repo.ensure_review(owner, item.id, revision.id)
                if row.version != command.expected_version:
                    raise fail("GRAPH_REVIEW_CONFLICT", ErrorCategory.CONFLICT)
                if command.status == "COMPLETE":
                    if row.status != "REVIEWING":
                        raise fail("GRAPH_REVIEW_NOT_STARTED", ErrorCategory.CONFLICT)
                    exists = repo.has_relations(owner, revision.id)
                    if (command.outcome == "RELATIONS") != exists:
                        raise fail("GRAPH_REVIEW_EVIDENCE_MISMATCH", ErrorCategory.CONFLICT)
                row.version += 1
                row.status, row.outcome, row.note = command.status, command.outcome, command.note
                row.updated_at = now()
                repo.record(owner, row, "REVIEW", f"{actor.issuer}:{actor.subject}")
                return snapshot(row)
        except IntegrityError:
            raise fail("GRAPH_REVIEW_CONFLICT", ErrorCategory.CONFLICT) from None

    def bind(self, actor: Actor, command: IdentityBind) -> dict[str, Any]:
        self.enabled()
        owner = owner_id(actor)
        try:
            with audited_uow(self.factory, actor, "GRAPH_IDENTITY_BIND", command) as uow:
                repo = GraphOpsRepository(uow.session)
                source = repo.source(
                    owner, str(command.evidence.knowledge_id), str(command.evidence.revision_id)
                )
                entity = repo.entity(owner, str(command.entity_id))
                if source is None or entity is None:
                    raise fail("GRAPH_IDENTITY_SOURCE_NOT_FOUND", ErrorCategory.NOT_FOUND)
                item, revision = source
                if entity.scope not in {"global", item.scope}:
                    raise fail("GRAPH_IDENTITY_SCOPE_MISMATCH")
                if command.status == "ACTIVE" and (
                    item.lifecycle_status != "ACTIVE" or item.active_revision_id != revision.id
                ):
                    raise fail("GRAPH_SOURCE_STALE", ErrorCategory.CONFLICT)
                if command.evidence.quote not in (revision.content_text or ""):
                    raise fail("GRAPH_EVIDENCE_INVALID")
                if command.status == "ACTIVE" and command.value not in command.evidence.quote:
                    raise fail("GRAPH_IDENTITY_VALUE_NOT_IN_QUOTE")
                normalized = command.value.lower() if command.kind == "alias" else command.value
                key = digest(
                    [
                        owner,
                        entity.scope,
                        command.kind,
                        command.namespace,
                        normalized,
                        entity.id if command.kind == "alias" else None,
                    ]
                )
                row = repo.binding(owner, key)
                if (row.version if row else 0) != command.expected_version:
                    raise fail("GRAPH_IDENTITY_CONFLICT", ErrorCategory.CONFLICT)
                if row is None:
                    if command.status == "RETRACTED":
                        raise fail("GRAPH_IDENTITY_NOT_FOUND", ErrorCategory.NOT_FOUND)
                    row = GraphIdentity(
                        id=uid(), owner_id=owner, scope=entity.scope, binding_key=key, version=0
                    )
                    uow.session.add(row)
                row.entity_id, row.kind = entity.id, command.kind
                row.namespace, row.value, row.status = command.namespace, command.value, command.status
                row.item_id, row.revision_id = item.id, revision.id
                row.quote, row.note = command.evidence.quote, command.note
                row.version += 1
                row.updated_at = now()
                repo.record(owner, row, "IDENTITY", f"{actor.issuer}:{actor.subject}")
                return snapshot(row)
        except IntegrityError:
            raise fail("GRAPH_IDENTITY_CONFLICT", ErrorCategory.CONFLICT) from None

    def resolve(self, actor: Actor, command: IdentityResolve) -> dict[str, Any]:
        self.enabled()
        owner, scopes = owner_id(actor), list(dict.fromkeys([*command.scopes, "global"]))
        with SqlAlchemyUnitOfWork(self.factory, read_only=True) as uow:
            repo = GraphOpsRepository(uow.session)
            bindings = repo.matches(owner, scopes, command.query, command.namespace)
            candidates: dict[str, dict[str, Any]] = {}
            bound_entities = (
                {
                    e.id: e
                    for e in GraphRepository(uow.session).entities(
                        owner, scopes, ids={b.entity_id for b in bindings[:100]}
                    )
                }
                if bindings
                else {}
            )
            for binding in bindings[:100]:
                entity = bound_entities.get(binding.entity_id)
                if entity is None:
                    continue
                entry = candidates.setdefault(
                    entity.id, {"entity": entity_view(entity), "matches": [], "exact": True}
                )
                entry["matches"].append({"reason": "evidenced_" + binding.kind, "binding": snapshot(binding)})
            canonical = repo.canonical(owner, scopes, command.query)
            hints = canonical + GraphRepository(uow.session).entities(owner, scopes, command.query)
            for entity in hints:
                exact = entity.identity_key == command.query
                entry = candidates.setdefault(
                    entity.id, {"entity": entity_view(entity), "matches": [], "exact": exact}
                )
                entry["exact"] = entry["exact"] or exact
                entry["matches"].append(
                    {"reason": "canonical_key" if exact else "label_or_legacy_alias_hint"}
                )
            rows = sorted(candidates.values(), key=lambda c: (not c["exact"], c["entity"]["id"]))
            exact_ids = [c["entity"]["id"] for c in rows if c["exact"]]
            return {
                "items": rows[:100],
                "ambiguous": len(exact_ids) > 1,
                "truncated": len(bindings) > 100 or len(hints) > 100 or len(rows) > 100,
                "automatic_merge": False,
                "guidance": "Candidates only. Confirm project/environment and exact evidence before reusing an entity. No fuzzy match establishes identity.",
            }

    def bindings(self, actor: Actor, entity_id: str, offset: int, limit: int) -> dict[str, Any]:
        with SqlAlchemyUnitOfWork(self.factory, read_only=True) as uow:
            rows = GraphOpsRepository(uow.session).bindings(owner_id(actor), entity_id, offset, limit)
            return {
                "items": [
                    {
                        **snapshot(row),
                        "evidence_current": item.lifecycle_status == "ACTIVE"
                        and item.active_revision_id == row.revision_id,
                    }
                    for row, item in rows[:limit]
                ],
                "next_offset": offset + limit if len(rows) > limit else None,
            }

    def history(self, actor: Actor, target_id: str, offset: int, limit: int) -> dict[str, Any]:
        with SqlAlchemyUnitOfWork(self.factory, read_only=True) as uow:
            rows = GraphOpsRepository(uow.session).history(owner_id(actor), target_id, offset, limit)
            return {
                "items": [
                    {
                        "kind": r.kind,
                        "version": r.version,
                        "actor": r.actor,
                        "at": r.created_at.isoformat(),
                        "snapshot": json.loads(r.snapshot_json),
                    }
                    for r in rows[:limit]
                ],
                "next_offset": offset + limit if len(rows) > limit else None,
            }

    def explore(self, actor: Actor, command: GraphExplore) -> dict[str, Any]:
        self.enabled()
        predicates = (
            ["documents", "part_of", "created_from"]
            if command.intent == "evidence"
            else ["uses", "depends_on", "created_from", "deployed_on", "part_of"]
        )
        data = command.search.model_dump()
        data.update(predicates=predicates, direction="both" if command.intent == "evidence" else "incoming")
        result = GraphService(self.factory, self.settings).search(actor, GraphSearch.model_validate(data))
        result["intent"] = command.intent
        result["interpretation"] = "Evidence-backed connectivity; not proof of causality or confirmed impact."
        return result
