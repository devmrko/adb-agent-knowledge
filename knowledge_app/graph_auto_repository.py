"""Persistence operations; transaction ownership stays with the service."""

from datetime import timedelta
from typing import Any

from sqlalchemy import exists, select, update
from sqlalchemy.orm import Session

from knowledge_app.graph_auto_contracts import SCHEMA_VERSION
from knowledge_app.graph_auto_models import ExtractionRun, GraphProposal
from knowledge_app.graph_repository import GraphRepository
from knowledge_app.graph_service import digest
from knowledge_app.models import GraphEntity, GraphEvidence, Item, Revision, now, uid


class AutoGraphRepository:
    def __init__(self, session: Session):
        self.session = session

    def enqueue(self, item: Item, model: str) -> ExtractionRun:
        key = digest([item.owner_id, item.active_revision_id, SCHEMA_VERSION, model])
        existing = self.session.scalar(select(ExtractionRun).where(ExtractionRun.run_key == key))
        if existing:
            return existing
        row = ExtractionRun(
            id=uid(),
            owner_id=item.owner_id,
            item_id=item.id,
            revision_id=item.active_revision_id,
            run_key=key,
            schema_version=SCHEMA_VERSION,
            model=model,
            status="PENDING",
            attempts=0,
            retry_limit=5,
            force_extract=0,
            available_at=now(),
            created_at=now(),
            updated_at=now(),
        )
        self.session.add(row)
        self.session.flush()
        return row

    def discover(self, model: str) -> None:
        row = self.session.scalar(
            select(Item)
            .join(Revision, Revision.id == Item.active_revision_id)
            .where(
                Item.lifecycle_status == "ACTIVE",
                Revision.content_text.is_not(None),
                ~exists(
                    select(ExtractionRun.id).where(
                        ExtractionRun.owner_id == Item.owner_id,
                        ExtractionRun.revision_id == Item.active_revision_id,
                        ExtractionRun.schema_version == SCHEMA_VERSION,
                        ExtractionRun.model == model,
                    )
                ),
            )
            .order_by(Revision.created_at, Revision.id)
            .limit(1)
        )
        if row is not None:
            self.enqueue(row, model)

    def claim(self, model: str) -> ExtractionRun | None:
        due = (ExtractionRun.available_at <= now()) & ExtractionRun.status.in_(["PENDING", "RUNNING"])
        ids = list(
            self.session.scalars(
                select(ExtractionRun.id)
                .join(Revision, Revision.id == ExtractionRun.revision_id)
                .where(due, ExtractionRun.model == model, ExtractionRun.schema_version == SCHEMA_VERSION)
                .order_by(Revision.created_at, ExtractionRun.id)
                .limit(10)
            )
        )
        for identifier in ids:
            row = self.session.scalar(
                select(ExtractionRun)
                .where(ExtractionRun.id == identifier, due)
                .with_for_update(skip_locked=True)
            )
            if row is None:
                continue
            if row.attempts >= row.retry_limit:
                row.status, row.error_code = "FAILED", "ATTEMPTS_EXHAUSTED"
                continue
            token = uid()
            result: Any = self.session.execute(
                update(ExtractionRun)
                .execution_options(synchronize_session=False)
                .where(ExtractionRun.id == identifier, due)
                .values(
                    status="RUNNING",
                    lease_token=token,
                    attempts=ExtractionRun.attempts + 1,
                    available_at=now() + timedelta(minutes=5),
                    updated_at=now(),
                )
            )
            if result.rowcount == 1:
                self.session.refresh(row)
                return row
        return None

    def source(self, run: ExtractionRun) -> tuple[Item, Revision] | None:
        result = GraphRepository(self.session).source(run.owner_id, run.item_id, run.revision_id)
        if (
            result
            and result[0].active_revision_id == run.revision_id
            and result[0].lifecycle_status == "ACTIVE"
        ):
            return result
        return None

    def required(self, item: Item) -> bool:
        return (
            item.memory_kind == "PROCEDURE"
            or item.knowledge_type == "TROUBLESHOOTING"
            or bool(
                self.session.scalar(
                    select(GraphEvidence.id)
                    .where(GraphEvidence.owner_id == item.owner_id, GraphEvidence.knowledge_id == item.id)
                    .limit(1)
                )
            )
        )

    def context(self, item: Item, content: str) -> list[dict[str, Any]]:
        # Bounded suggestions only. Labels/aliases never establish identity.
        rows = list(
            self.session.scalars(
                select(GraphEntity)
                .where(GraphEntity.owner_id == item.owner_id, GraphEntity.scope.in_(["global", item.scope]))
                .order_by(GraphEntity.id)
                .limit(501)
            )
        )
        return [
            dict(id=e.id, label=e.label, kind=e.kind, identity_key=e.identity_key, scope=e.scope)
            for e in rows
            if e.label in content or e.identity_key in content
        ][:100]

    def owned_run(self, owner: str, identifier: str, lock: bool = False) -> ExtractionRun | None:
        query = select(ExtractionRun).where(ExtractionRun.id == identifier, ExtractionRun.owner_id == owner)
        return self.session.scalar(query.with_for_update() if lock else query)

    def owned_proposal(self, owner: str, identifier: str) -> GraphProposal | None:
        return self.session.scalar(
            select(GraphProposal)
            .where(GraphProposal.id == identifier, GraphProposal.owner_id == owner)
            .with_for_update()
        )

    def listing(self, owner: str, proposals: bool, item_id: str | None, offset: int, limit: int) -> list[Any]:
        model = GraphProposal if proposals else ExtractionRun
        query = select(model).where(model.owner_id == owner)
        if item_id:
            query = query.where(model.item_id == item_id)
        return list(
            self.session.scalars(
                query.order_by(model.created_at.desc(), model.id).offset(offset).limit(limit + 1)
            )
        )

    def stale(self, proposal: GraphProposal) -> bool:
        item = self.session.get(Item, proposal.item_id)
        return (
            item is None
            or item.owner_id != proposal.owner_id
            or item.lifecycle_status != "ACTIVE"
            or item.active_revision_id != proposal.revision_id
        )
