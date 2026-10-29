from datetime import datetime
from typing import Any

from sqlalchemy import and_, bindparam, func, or_, select, text
from sqlalchemy.orm import Session

from knowledge_app.graph_contracts import GraphSearch
from knowledge_app.models import Event, GraphClaim, GraphEntity, GraphEvidence, GraphVersion, Item, Revision


class GraphRepository:
    def __init__(self, session: Session, property_graph: bool = False):
        self.session = session
        self.property_graph = property_graph

    def entities(
        self, owner: str, scopes: list[str] | None, query: str = "", ids: set[str] | None = None
    ) -> list[GraphEntity]:
        stmt = select(GraphEntity).where(GraphEntity.owner_id == owner)
        if scopes:
            stmt = stmt.where(GraphEntity.scope.in_(scopes))
        if ids is not None:
            stmt = stmt.where(GraphEntity.id.in_(ids))
        if query.strip():
            terms = list(dict.fromkeys(query.lower().split()))[:12]
            stmt = stmt.where(
                or_(
                    *[func.lower(GraphEntity.aliases_json).contains(t, autoescape=True) for t in terms],
                    *[
                        GraphEntity.label.ilike(
                            "%" + t.replace("%", "\\%").replace("_", "\\_") + "%", escape="\\"
                        )
                        for t in terms
                    ],
                    *[
                        GraphEntity.identity_key.ilike(
                            "%" + t.replace("%", "\\%").replace("_", "\\_") + "%", escape="\\"
                        )
                        for t in terms
                    ],
                )
            )
        return list(
            self.session.scalars(
                stmt.order_by(GraphEntity.label, GraphEntity.id).limit(201 if ids is not None else 101)
            )
        )

    def entity_by_key(self, identity_hash: str) -> GraphEntity | None:
        return self.session.scalar(select(GraphEntity).where(GraphEntity.identity_hash == identity_hash))

    def claim(
        self, owner: str, *, claim_id: str | None = None, signature: str | None = None
    ) -> GraphClaim | None:
        stmt = select(GraphClaim).where(GraphClaim.owner_id == owner)
        stmt = (
            stmt.where(GraphClaim.id == claim_id)
            if claim_id
            else stmt.where(GraphClaim.signature == signature)
        )
        return self.session.scalar(stmt.with_for_update())

    def versions(self, owner: str, claim_id: str) -> list[GraphVersion]:
        return list(
            self.session.scalars(
                select(GraphVersion)
                .where(GraphVersion.owner_id == owner, GraphVersion.claim_id == claim_id)
                .order_by(GraphVersion.recorded_from)
            )
        )

    def evidence(self, owner: str, version_id: str) -> list[GraphEvidence]:
        return list(
            self.session.scalars(
                select(GraphEvidence).where(
                    GraphEvidence.owner_id == owner, GraphEvidence.version_id == version_id
                )
            )
        )

    def candidates(
        self,
        owner: str,
        command: GraphSearch,
        known: datetime,
        valid: datetime,
        frontier: set[str] | None,
        knowledge_id: str | None = None,
        seed_revisions: list[tuple[str, str]] | None = None,
    ) -> list[GraphVersion]:
        stmt = select(GraphVersion).where(
            GraphVersion.owner_id == owner,
            GraphVersion.recorded_from <= known,
            or_(GraphVersion.recorded_to.is_(None), GraphVersion.recorded_to > known),
            GraphVersion.status == "ACTIVE",
        )
        if command.predicates:
            stmt = stmt.where(GraphVersion.predicate.in_(command.predicates))
        if command.scopes:
            allowed = list(set(command.scopes) | {"global"})
            visible = select(GraphEntity.id).where(
                GraphEntity.owner_id == owner, GraphEntity.scope.in_(allowed)
            )
            stmt = stmt.where(
                GraphVersion.scope.in_(allowed),
                GraphVersion.subject_id.in_(visible),
                or_(GraphVersion.object_id.is_(None), GraphVersion.object_id.in_(visible)),
            )
        temporal: list[Any] = [
            GraphVersion.temporal_kind == "TIMELESS",
            (GraphVersion.temporal_kind == "INTERVAL")
            & (GraphVersion.valid_from <= valid)
            & or_(GraphVersion.valid_to.is_(None), GraphVersion.valid_to > valid),
        ]
        if command.valid_at is None or command.include_undated:
            temporal.append(GraphVersion.temporal_kind == "UNKNOWN")
        stmt = stmt.where(or_(*temporal))
        if frontier and self.property_graph and self.session.get_bind().dialect.name == "oracle":
            # Property Graph provides candidates only; RDB/evidence filters remain authoritative.
            graph_ids = (
                text("""
                SELECT version_id FROM GRAPH_TABLE (VK_KNOWLEDGE_GRAPH
                    MATCH (s IS entity)-[e IS relation]->(t IS entity)
                    WHERE e.owner_id = :pg_owner
                    COLUMNS (e.id AS version_id, s.id AS source_id, t.id AS target_id)
                ) WHERE source_id IN :pg_frontier OR target_id IN :pg_frontier
            """)
                .bindparams(
                    bindparam("pg_owner", value=owner),
                    bindparam("pg_frontier", value=sorted(frontier), expanding=True),
                )
                .columns(version_id=GraphVersion.id.type)
            )
            # Literal relations do not have a destination vertex; retain the RDB path for them.
            stmt = stmt.where(or_(GraphVersion.id.in_(graph_ids), GraphVersion.object_id.is_(None)))
        if frontier is not None:
            if command.direction == "outgoing":
                stmt = stmt.where(GraphVersion.subject_id.in_(frontier))
            elif command.direction == "incoming":
                stmt = stmt.where(GraphVersion.object_id.in_(frontier))
            else:
                stmt = stmt.where(
                    or_(GraphVersion.subject_id.in_(frontier), GraphVersion.object_id.in_(frontier))
                )
        if seed_revisions:
            stmt = stmt.where(
                GraphVersion.id.in_(
                    select(GraphEvidence.version_id).where(
                        GraphEvidence.owner_id == owner,
                        or_(
                            *[
                                and_(GraphEvidence.knowledge_id == kid, GraphEvidence.revision_id == rid)
                                for kid, rid in seed_revisions
                            ]
                        ),
                    )
                )
            )
        if knowledge_id:
            stmt = stmt.where(
                GraphVersion.id.in_(
                    select(GraphEvidence.version_id).where(
                        GraphEvidence.owner_id == owner, GraphEvidence.knowledge_id == knowledge_id
                    )
                )
            )
        return list(
            self.session.scalars(stmt.order_by(GraphVersion.recorded_from.desc(), GraphVersion.id).limit(501))
        )

    def source(self, owner: str, knowledge_id: str, revision_id: str) -> tuple[Item, Revision] | None:
        row = self.session.execute(
            select(Item, Revision)
            .join(Revision, (Revision.item_id == Item.id) & (Revision.owner_id == Item.owner_id))
            .where(Item.owner_id == owner, Item.id == knowledge_id, Revision.id == revision_id)
        ).first()
        return (row[0], row[1]) if row else None

    def source_events(self, owner: str, item_id: str, known: datetime) -> list[Event]:
        return list(
            self.session.scalars(
                select(Event)
                .where(Event.owner_id == owner, Event.item_id == item_id, Event.created_at <= known)
                .order_by(Event.created_at)
            )
        )
