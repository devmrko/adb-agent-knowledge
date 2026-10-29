import json
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from knowledge_app.graph_ops_models import GraphIdentity, GraphOperation, GraphReview
from knowledge_app.models import GraphEntity, GraphEvidence, GraphVersion, Item, Revision, now, uid


def snapshot(row: Any) -> dict[str, Any]:
    return {
        c.name: (getattr(row, c.name).isoformat() if c.name == "updated_at" else getattr(row, c.name))
        for c in row.__table__.columns
        if c.name not in {"owner_id", "binding_key"}
    }


class GraphOpsRepository:
    def __init__(self, session: Session):
        self.session = session

    def source(self, owner: str, item_id: str, revision_id: str) -> tuple[Item, Revision] | None:
        item = self.session.scalar(
            select(Item).where(Item.owner_id == owner, Item.id == item_id).with_for_update()
        )
        if item is None:
            return None
        revision = self.session.scalar(
            select(Revision).where(
                Revision.owner_id == owner, Revision.item_id == item_id, Revision.id == revision_id
            )
        )
        return (item, revision) if revision else None

    def review(self, owner: str, revision_id: str) -> GraphReview | None:
        return self.session.scalar(
            select(GraphReview)
            .where(GraphReview.owner_id == owner, GraphReview.revision_id == revision_id)
            .with_for_update()
        )

    def ensure_review(self, owner: str, item_id: str, revision_id: str) -> GraphReview:
        row = self.review(owner, revision_id)
        if row is None:
            row = GraphReview(
                id=uid(),
                owner_id=owner,
                item_id=item_id,
                revision_id=revision_id,
                version=0,
                status="PENDING",
                outcome=None,
                note="Source revision ready",
                updated_at=now(),
            )
            self.session.add(row)
            self.session.flush()
            self.record(owner, row, "REVIEW", "system:source-ready")
        return row

    def backlog(self, owner: str, scopes: list[str] | None, offset: int, limit: int) -> list[Any]:
        stmt = (
            select(Item, GraphReview)
            .outerjoin(
                GraphReview,
                (GraphReview.owner_id == Item.owner_id)
                & (GraphReview.revision_id == Item.active_revision_id),
            )
            .where(
                Item.owner_id == owner,
                Item.lifecycle_status == "ACTIVE",
                Item.active_revision_id.is_not(None),
                or_(GraphReview.id.is_(None), GraphReview.status != "COMPLETE"),
            )
        )
        if scopes:
            stmt = stmt.where(Item.scope.in_(scopes))
        return list(self.session.execute(stmt.order_by(Item.id).offset(offset).limit(limit + 1)))

    def has_relations(self, owner: str, revision_id: str) -> bool:
        return (
            self.session.scalar(
                select(GraphEvidence.id)
                .join(
                    GraphVersion,
                    (GraphEvidence.version_id == GraphVersion.id)
                    & (GraphEvidence.owner_id == GraphVersion.owner_id),
                )
                .where(
                    GraphEvidence.owner_id == owner,
                    GraphEvidence.revision_id == revision_id,
                    GraphVersion.status == "ACTIVE",
                    GraphVersion.recorded_to.is_(None),
                )
                .limit(1)
            )
            is not None
        )

    def entity(self, owner: str, identifier: str) -> GraphEntity | None:
        return self.session.scalar(
            select(GraphEntity).where(GraphEntity.owner_id == owner, GraphEntity.id == identifier)
        )

    def binding(self, owner: str, key: str) -> GraphIdentity | None:
        return self.session.scalar(
            select(GraphIdentity)
            .where(GraphIdentity.owner_id == owner, GraphIdentity.binding_key == key)
            .with_for_update()
        )

    def bindings(self, owner: str, entity_id: str, offset: int, limit: int) -> list[Any]:
        return list(
            self.session.execute(
                select(GraphIdentity, Item)
                .join(Item, (Item.id == GraphIdentity.item_id) & (Item.owner_id == GraphIdentity.owner_id))
                .where(GraphIdentity.owner_id == owner, GraphIdentity.entity_id == entity_id)
                .order_by(GraphIdentity.id)
                .offset(offset)
                .limit(limit + 1)
            )
        )

    def canonical(self, owner: str, scopes: list[str], query: str) -> list[GraphEntity]:
        return list(
            self.session.scalars(
                select(GraphEntity)
                .where(
                    GraphEntity.owner_id == owner,
                    GraphEntity.scope.in_(scopes),
                    GraphEntity.identity_key == query,
                )
                .order_by(GraphEntity.id)
                .limit(101)
            )
        )

    def matches(
        self, owner: str, scopes: list[str], query: str, namespace: str | None
    ) -> list[GraphIdentity]:
        stmt = (
            select(GraphIdentity)
            .join(Item, (Item.id == GraphIdentity.item_id) & (Item.owner_id == GraphIdentity.owner_id))
            .where(
                GraphIdentity.owner_id == owner,
                GraphIdentity.scope.in_(scopes),
                Item.scope.in_(scopes),
                GraphIdentity.status == "ACTIVE",
                Item.lifecycle_status == "ACTIVE",
                Item.active_revision_id == GraphIdentity.revision_id,
                or_(
                    (GraphIdentity.kind == "alias") & (func.lower(GraphIdentity.value) == query.lower()),
                    (GraphIdentity.kind == "external") & (GraphIdentity.value == query),
                ),
            )
        )
        if namespace:
            stmt = stmt.where(GraphIdentity.namespace == namespace)
        return list(self.session.scalars(stmt.order_by(GraphIdentity.id).limit(101)))

    def record(self, owner: str, row: Any, kind: str, actor: str) -> None:
        self.session.add(
            GraphOperation(
                id=uid(),
                owner_id=owner,
                target_id=row.id,
                kind=kind,
                version=row.version,
                actor=actor,
                snapshot_json=json.dumps(snapshot(row), ensure_ascii=False),
                created_at=now(),
            )
        )

    def history(self, owner: str, target_id: str, offset: int, limit: int) -> list[GraphOperation]:
        return list(
            self.session.scalars(
                select(GraphOperation)
                .where(GraphOperation.owner_id == owner, GraphOperation.target_id == target_id)
                .order_by(GraphOperation.version.desc())
                .offset(offset)
                .limit(limit + 1)
            )
        )
