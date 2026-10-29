import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from knowledge_app import shared_rdf
from knowledge_app.audit_context import audited_uow
from knowledge_app.graph_contracts import AssertionInput, AssertionRevision, EntityInput, GraphSearch
from knowledge_app.graph_repository import GraphRepository
from knowledge_app.graph_results import enrich_graph
from knowledge_app.models import GraphClaim, GraphEntity, GraphEvidence, GraphVersion, now, uid
from knowledge_app.service import fail, owner_id
from knowledge_app.settings import Settings
from python_foundation.database import SqlAlchemyUnitOfWork
from python_foundation.errors import ErrorCategory
from python_foundation.security import Actor


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def entity_view(entity: GraphEntity) -> dict[str, Any]:
    return {
        "id": entity.id,
        "label": entity.label,
        "scope": entity.scope,
        "kind": entity.kind,
        "identity_key": entity.identity_key,
        "aliases": json.loads(entity.aliases_json),
    }


class GraphService:
    def __init__(self, factory: sessionmaker[Session], settings: Settings):
        self.factory, self.settings = factory, settings

    def enabled(self) -> None:
        if not self.settings.workflow_rdf_enabled:
            raise fail("WORKFLOW_DISABLED", ErrorCategory.UNAVAILABLE)

    def entity(self, actor: Actor, command: EntityInput) -> dict[str, Any]:
        self.enabled()
        owner = owner_id(actor)
        key = digest([owner, command.scope, command.identity_key])
        try:
            with audited_uow(self.factory, actor, "GRAPH_SERVICE_ENTITY", command) as uow:
                repo = GraphRepository(uow.session)
                existing = repo.entity_by_key(key)
                if existing:
                    if existing.label != command.label or existing.kind != command.kind:
                        raise fail("ENTITY_IDENTITY_CONFLICT", ErrorCategory.CONFLICT)
                    return entity_view(existing)
                entity = GraphEntity(
                    owner_id=owner,
                    scope=command.scope,
                    identity_hash=key,
                    identity_key=command.identity_key,
                    label=command.label,
                    kind=command.kind,
                    aliases_json=json.dumps(command.aliases, ensure_ascii=False),
                )
                uow.session.add(entity)
                uow.session.flush()
                return entity_view(entity)
        except IntegrityError:
            raise fail("GRAPH_CONCURRENT_UPDATE", ErrorCategory.CONFLICT) from None

    def entities(self, actor: Actor, query: str, scopes: list[str] | None) -> dict[str, Any]:
        with SqlAlchemyUnitOfWork(self.factory, read_only=True) as uow:
            rows = GraphRepository(uow.session).entities(owner_id(actor), scopes, query)
            return {"items": [entity_view(e) for e in rows[:100]], "truncated": len(rows) > 100}

    def assertion(self, actor: Actor, command: AssertionInput, claim_id: str | None = None) -> dict[str, Any]:
        self.enabled()
        owner = owner_id(actor)
        payload = command.model_dump(mode="json", exclude={"expected_version_id"})
        signature_data = {
            k: payload[k]
            for k in (
                "scope",
                "subject_id",
                "predicate",
                "object_id",
                "literal",
                "condition",
                "temporal_kind",
                "valid_from",
                "valid_to",
            )
        }
        for key in ("valid_from", "valid_to"):
            value = getattr(command, key)
            if value:
                signature_data[key] = utc(value).isoformat()
        signature = digest([owner, signature_data])
        try:
            with audited_uow(self.factory, actor, "GRAPH_SERVICE_ASSERTION", command) as uow:
                repo = GraphRepository(uow.session)
                nodes = repo.entities(
                    owner,
                    None if command.scope == "global" else ["global", command.scope],
                    ids={str(command.subject_id)}
                    | ({str(command.object_id)} if command.object_id else set()),
                )
                if len(nodes) != len(
                    {str(command.subject_id)} | ({str(command.object_id)} if command.object_id else set())
                ):
                    raise fail("GRAPH_ENTITY_NOT_FOUND", ErrorCategory.NOT_FOUND)
                for evidence in command.evidence:
                    source = repo.source(owner, str(evidence.knowledge_id), str(evidence.revision_id))
                    if not source or (
                        command.scope != "global" and source[0].scope not in {"global", command.scope}
                    ):
                        raise fail("GRAPH_SOURCE_NOT_FOUND", ErrorCategory.NOT_FOUND)
                    item, revision = source
                    if item.lifecycle_status != "ACTIVE" or item.active_revision_id != revision.id:
                        raise fail("GRAPH_SOURCE_NOT_ACTIVE", ErrorCategory.CONFLICT)
                    if not evidence.quote.strip() or evidence.quote not in (revision.content_text or ""):
                        raise fail("GRAPH_EVIDENCE_MISMATCH")
                if (
                    command.temporal_basis
                    and not command.temporal_basis.user_asserted
                    and not any(command.temporal_basis.text in e.quote for e in command.evidence)
                ):
                    raise fail("GRAPH_TIME_BASIS_MISMATCH")
                claim = repo.claim(owner, claim_id=claim_id, signature=signature)
                if claim_id and claim is None:
                    raise fail("GRAPH_ASSERTION_NOT_FOUND", ErrorCategory.NOT_FOUND)
                old = (
                    uow.session.get(GraphVersion, claim.current_version_id)
                    if claim and claim.current_version_id
                    else None
                )
                if claim_id:
                    if (
                        not isinstance(command, AssertionRevision)
                        or old is None
                        or old.id != str(command.expected_version_id)
                    ):
                        raise fail("GRAPH_VERSION_CONFLICT", ErrorCategory.CONFLICT)
                    if claim and claim.scope != command.scope:
                        raise fail("GRAPH_SCOPE_IMMUTABLE", ErrorCategory.CONFLICT)
                elif old:
                    previous = json.loads(old.payload_json)
                    if old.status != "ACTIVE" or command.status != "ACTIVE":
                        raise fail("GRAPH_REVISION_REQUIRED", ErrorCategory.CONFLICT)
                    combined = {
                        json.dumps(e, sort_keys=True): e for e in previous["evidence"] + payload["evidence"]
                    }
                    payload = previous
                    payload["evidence"] = list(combined.values())
                    if len(payload["evidence"]) > 50:
                        raise fail("GRAPH_EVIDENCE_LIMIT")
                if command.status == "RETRACTED" and not claim_id:
                    raise fail("GRAPH_REVISION_REQUIRED")
                payload["evidence"] = sorted(payload["evidence"], key=lambda e: json.dumps(e, sort_keys=True))
                if old and json.loads(old.payload_json) == payload:
                    return {
                        "assertion_id": old.claim_id,
                        "version_id": old.id,
                        "status": "READY",
                        "unchanged": True,
                    }
                if claim is None:
                    claim = GraphClaim(owner_id=owner, scope=command.scope, signature=signature)
                    uow.session.add(claim)
                    uow.session.flush()
                recorded = now()
                native = uow.session.get_bind().dialect.name == "oracle"
                if old:
                    old.recorded_to = recorded
                    if native:
                        shared_rdf.close(uow.session, owner, old.id, recorded)
                version = GraphVersion(
                    id=uid(),
                    owner_id=owner,
                    claim_id=claim.id,
                    scope=command.scope,
                    subject_id=str(command.subject_id),
                    object_id=str(command.object_id) if command.object_id else None,
                    predicate=command.predicate,
                    temporal_kind=command.temporal_kind,
                    valid_from=utc(command.valid_from) if command.valid_from else None,
                    valid_to=utc(command.valid_to) if command.valid_to else None,
                    recorded_from=recorded,
                    status=command.status,
                    payload_json=json.dumps(payload, ensure_ascii=False, sort_keys=True),
                )
                uow.session.add(version)
                uow.session.flush()
                for evidence in payload["evidence"]:
                    uow.session.add(GraphEvidence(owner_id=owner, version_id=version.id, **evidence))
                if native:
                    shared_rdf.insert(uow.session, owner, version.id, claim.id, payload, recorded)
                    shared_rdf.verify(uow.session, owner, version.id, claim.id, payload, recorded, None)
                claim.signature, claim.current_version_id = signature, version.id
                uow.session.flush()
                return {
                    "assertion_id": claim.id,
                    "version_id": version.id,
                    "recorded_from": recorded.isoformat(),
                    "status": "READY",
                    "unchanged": False,
                    "storage": "oracle_rdf" if native else "sqlite_test",
                }
        except IntegrityError:
            raise fail("GRAPH_CONCURRENT_OR_DUPLICATE_CONFLICT", ErrorCategory.CONFLICT) from None
        except (SQLAlchemyError, ValueError):
            raise fail("GRAPH_STORAGE_UNAVAILABLE", ErrorCategory.UNAVAILABLE) from None

    def evidence_at(
        self,
        repo: GraphRepository,
        owner: str,
        version: GraphVersion,
        known: datetime,
        historical: bool,
        scopes: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        result = []
        for evidence in repo.evidence(owner, version.id):
            source = repo.source(owner, evidence.knowledge_id, evidence.revision_id)
            if not source:
                continue
            item, revision = source
            if scopes and item.scope not in set(scopes) | {"global"}:
                continue
            if not historical:
                eligible = item.lifecycle_status == "ACTIVE" and item.active_revision_id == revision.id
            else:
                events = repo.source_events(owner, item.id, known)
                lifecycle = [e for e in events if e.event_type in {"RETIRED", "RESTORED"}]
                activations = [e for e in events if e.event_type == "SOURCE_ACTIVATED"]
                eligible = (
                    (not lifecycle or lifecycle[-1].event_type == "RESTORED")
                    and (not activations or activations[-1].revision_id == revision.id)
                    and utc(revision.created_at) <= known
                )
            if eligible:
                result.append(
                    {
                        "knowledge_id": item.id,
                        "revision_id": revision.id,
                        "title": item.title,
                        "quote": evidence.quote,
                        "content_uri": f"/api/v1/knowledge/{item.id}/revisions/{revision.id}/content",
                    }
                )
        return result

    def history(self, actor: Actor, claim_id: str) -> dict[str, Any]:
        with SqlAlchemyUnitOfWork(self.factory, read_only=True) as uow:
            repo = GraphRepository(uow.session)
            versions = repo.versions(owner_id(actor), claim_id)
            if not versions:
                raise fail("GRAPH_ASSERTION_NOT_FOUND", ErrorCategory.NOT_FOUND)
            return {
                "assertion_id": claim_id,
                "versions": [
                    {
                        "version_id": v.id,
                        "recorded_from": utc(v.recorded_from).isoformat(),
                        "recorded_to": utc(v.recorded_to).isoformat() if v.recorded_to else None,
                        **json.loads(v.payload_json),
                    }
                    for v in versions
                ],
            }

    def search(self, actor: Actor, command: GraphSearch) -> dict[str, Any]:
        self.enabled()
        if (
            command.include_entity_matches
            and command.seed_revisions
            and (command.query.strip() or command.entity_ids)
        ):
            sources = self.search(
                actor,
                command.model_copy(update={"query": "", "entity_ids": [], "include_entity_matches": False}),
            )
            entities = self.search(
                actor, command.model_copy(update={"seed_revisions": [], "include_entity_matches": False})
            )
            # Interleave lanes so neither silently monopolizes the shared budget.
            unique: dict[str, Any] = {}
            for n in range(max(len(sources["edges"]), len(entities["edges"]))):
                for lane in (entities, sources):
                    if n < len(lane["edges"]):
                        edge = lane["edges"][n]
                        unique.setdefault(edge["version_id"], edge)
            sources["edges"] = list(unique.values())[: command.max_edges]
            ids = {e[k] for e in sources["edges"] for k in ("source", "target")}
            sources["nodes"] = list(
                {n["id"]: n for lane in (sources, entities) for n in lane["nodes"] if n["id"] in ids}.values()
            )
            sources["seed_entity_ids"] = sorted(
                set(sources["seed_entity_ids"]) | set(entities["seed_entity_ids"])
            )
            sources["truncated"] |= entities["truncated"] or len(unique) > command.max_edges
            sources["retrieval_lanes"] = ["source", "entity"]
            return enrich_graph(sources, command.direction, command.depth)
        owner, known, valid = owner_id(actor), utc(command.known_at or now()), utc(command.valid_at or now())
        try:
            with SqlAlchemyUnitOfWork(self.factory, read_only=True) as uow:
                repo = GraphRepository(uow.session, self.settings.property_graph_enabled)
                seed_ids = {str(i) for i in command.entity_ids}
                if command.query.strip():
                    seed_ids.update(
                        e.id
                        for e in repo.entities(
                            owner,
                            list(set(command.scopes) | {"global"}) if command.scopes else None,
                            command.query,
                        )
                    )
                frontier: set[str] | None = seed_ids if seed_ids or command.query.strip() else None
                if command.knowledge_id or command.seed_revisions:
                    frontier = None
                source_seeds = {(str(s.knowledge_id), str(s.revision_id)) for s in command.seed_revisions}
                result: dict[str, Any] = {}
                truncated = False
                for level in range(command.depth + 1):
                    rows = repo.candidates(
                        owner,
                        command,
                        known,
                        valid,
                        frontier,
                        str(command.knowledge_id) if level == 0 and command.knowledge_id else None,
                        sorted(source_seeds) if level == 0 else None,
                    )
                    truncated |= len(rows) > 500
                    next_ids = set()
                    for version in rows[:500]:
                        if version.id in result:
                            continue
                        evidence = self.evidence_at(
                            repo, owner, version, known, command.known_at is not None, command.scopes
                        )
                        if not evidence:
                            continue
                        if (
                            level == 0
                            and source_seeds
                            and not any(
                                (e["knowledge_id"], e["revision_id"]) in source_seeds for e in evidence
                            )
                        ):
                            continue
                        if len(result) >= command.max_edges:
                            truncated = True
                            break
                        payload = json.loads(version.payload_json)
                        if uow.session.get_bind().dialect.name == "oracle":
                            shared_rdf.verify(
                                uow.session,
                                owner,
                                version.id,
                                version.claim_id,
                                payload,
                                version.recorded_from,
                                version.recorded_to,
                            )
                        result[version.id] = {
                            **payload,
                            "evidence": evidence,
                            "retrieval_level": level,
                            "assertion_id": version.claim_id,
                            "version_id": version.id,
                            "source": version.subject_id,
                            "target": version.object_id or "literal:" + version.id,
                            "relation": version.predicate,
                            "recorded_from": utc(version.recorded_from).isoformat(),
                            "recorded_to": utc(version.recorded_to).isoformat()
                            if version.recorded_to
                            else None,
                        }
                        if command.direction != "outgoing":
                            next_ids.add(version.subject_id)
                        if version.object_id and command.direction != "incoming":
                            next_ids.add(version.object_id)
                        if level == 0 and (command.knowledge_id or command.seed_revisions):
                            seed_ids.add(version.subject_id)
                            if version.object_id:
                                seed_ids.add(version.object_id)
                    if not next_ids or len(result) >= command.max_edges:
                        break
                    frontier = next_ids
                ids = {
                    e[k]
                    for e in result.values()
                    for k in ("source", "target")
                    if not e[k].startswith("literal:")
                }
                nodes = [
                    entity_view(e)
                    for e in repo.entities(
                        owner, list(set(command.scopes) | {"global"}) if command.scopes else None, ids=ids
                    )
                ]
                nodes += [
                    {"id": e["target"], "label": e["literal"], "kind": "literal"}
                    for e in result.values()
                    if e["literal"] is not None
                ]
                return enrich_graph(
                    {
                        "status": "READY",
                        "seed_entity_ids": sorted(seed_ids),
                        "evidence_state": "historical" if command.known_at else "current_revision_only",
                        "retrieval_lanes": [
                            "source" if command.knowledge_id or command.seed_revisions else "entity"
                        ],
                        "nodes": nodes,
                        "edges": list(result.values()),
                        "truncated": truncated,
                        "valid_at": valid.isoformat(),
                        "known_at": known.isoformat(),
                        "include_undated": command.include_undated or command.valid_at is None,
                        "seed_revisions": [s.model_dump(mode="json") for s in command.seed_revisions],
                        "candidate_backend": "oracle_property_graph"
                        if self.settings.property_graph_enabled
                        and uow.session.get_bind().dialect.name == "oracle"
                        else "relational",
                        "storage": "oracle_rdf"
                        if uow.session.get_bind().dialect.name == "oracle"
                        else "sqlite_test",
                    },
                    command.direction,
                    command.depth,
                )
        except (SQLAlchemyError, ValueError):
            raise fail("GRAPH_STORAGE_UNAVAILABLE", ErrorCategory.UNAVAILABLE) from None
