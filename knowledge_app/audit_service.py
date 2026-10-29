"""Owner-scoped change history and transactional, retryable derived-work consumer."""

import json
import logging
from datetime import timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from knowledge_app import navigation_rdf
from knowledge_app.audit_context import audited_uow
from knowledge_app.audit_models import ChangeContext, ChangeEvent, ChangeOutbox, ChangeReview
from knowledge_app.models import GraphClaim, GraphEvidence, Item, Revision, now, uid
from knowledge_app.service import fail, owner_id
from knowledge_app.summaries import extract_summary
from python_foundation.database import SqlAlchemyUnitOfWork
from python_foundation.errors import ErrorCategory
from python_foundation.security import Actor


class ResolveReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str = Field(min_length=1, max_length=1000)

    @field_validator("note")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Resolution note required")
        return value.strip()


def event_view(
    row: ChangeEvent, context: ChangeContext | None, outbox: ChangeOutbox | None, detail: bool = False
) -> dict[str, Any]:
    before, after = json.loads(row.before_json or "{}"), json.loads(row.after_json or "{}")
    result = {
        "id": row.id,
        "table_name": row.table_name,
        "target_id": row.target_id,
        "action": row.action,
        "created_at": row.created_at.isoformat(),
        "source": context.source if context else "DIRECT_SQL",
        "operation": context.operation if context else "DIRECT_SQL",
        "request_id": context.request_id if context else None,
        "actor_subject": context.actor_subject if context else None,
        "actor_issuer": context.actor_issuer if context else None,
        "machine_id": context.machine_id if context else None,
        "edit_origin": context.edit_origin if context else None,
        "reason": context.reason if context else None,
        "db_user": row.db_user,
        "changed_fields": sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k)),
        "outbox": {"status": outbox.status, "attempts": outbox.attempts, "error_code": outbox.error_code}
        if outbox
        else None,
    }
    if detail:
        result.update(before=before if row.before_json else None, after=after if row.after_json else None)
    return result


class AuditService:
    def __init__(self, factory: sessionmaker[Session], rdf_enabled: bool = False):
        self.factory, self.rdf_enabled = factory, rdf_enabled

    def changes(
        self,
        actor: Actor,
        *,
        table: str | None = None,
        target_id: str | None = None,
        offset: int = 0,
        limit: int = 30,
    ) -> dict[str, Any]:
        with SqlAlchemyUnitOfWork(self.factory, read_only=True) as uow:
            statement = (
                select(ChangeEvent, ChangeContext, ChangeOutbox)
                .outerjoin(
                    ChangeContext,
                    (ChangeContext.id == ChangeEvent.context_id)
                    & (ChangeContext.owner_id == ChangeEvent.owner_id),
                )
                .outerjoin(
                    ChangeOutbox,
                    (ChangeOutbox.event_id == ChangeEvent.id)
                    & (ChangeOutbox.owner_id == ChangeEvent.owner_id),
                )
                .where(ChangeEvent.owner_id == owner_id(actor))
            )
            if table:
                statement = statement.where(ChangeEvent.table_name == table)
            if target_id:
                statement = statement.where(ChangeEvent.target_id == target_id)
            rows = uow.session.execute(
                statement.order_by(ChangeEvent.created_at.desc(), ChangeEvent.id.desc())
                .offset(offset)
                .limit(limit + 1)
            ).all()
            return {
                "items": [event_view(*row) for row in rows[:limit]],
                "next_offset": offset + limit if len(rows) > limit else None,
            }

    def get(self, actor: Actor, event_id: str) -> dict[str, Any]:
        with SqlAlchemyUnitOfWork(self.factory, read_only=True) as uow:
            row = uow.session.get(ChangeEvent, event_id)
            if row is None or row.owner_id != owner_id(actor):
                raise fail("CHANGE_NOT_FOUND", ErrorCategory.NOT_FOUND)
            context = uow.session.get(ChangeContext, row.context_id) if row.context_id else None
            if context and context.owner_id != row.owner_id:
                context = None
            return event_view(row, context, uow.session.get(ChangeOutbox, event_id), True)

    def reviews(
        self, actor: Actor, status: Literal["OPEN", "RESOLVED"] = "OPEN", offset: int = 0, limit: int = 30
    ) -> dict[str, Any]:
        with SqlAlchemyUnitOfWork(self.factory, read_only=True) as uow:
            rows = list(
                uow.session.scalars(
                    select(ChangeReview)
                    .where(ChangeReview.owner_id == owner_id(actor), ChangeReview.status == status)
                    .order_by(ChangeReview.created_at.desc(), ChangeReview.id)
                    .offset(offset)
                    .limit(limit + 1)
                )
            )
            return {
                "items": [
                    {
                        c.name: getattr(row, c.name)
                        for c in ChangeReview.__table__.columns
                        if c.name != "owner_id"
                    }
                    for row in rows[:limit]
                ],
                "next_offset": offset + limit if len(rows) > limit else None,
            }

    def resolve(self, actor: Actor, review_id: str, command: ResolveReview) -> dict[str, Any]:
        with SqlAlchemyUnitOfWork(self.factory) as uow:
            row = uow.session.scalar(
                select(ChangeReview)
                .where(ChangeReview.id == review_id, ChangeReview.owner_id == owner_id(actor))
                .with_for_update()
            )
            if row is None:
                raise fail("REVIEW_NOT_FOUND", ErrorCategory.NOT_FOUND)
            if row.status == "RESOLVED":
                if row.resolution_note != command.note:
                    raise fail("REVIEW_ALREADY_RESOLVED", ErrorCategory.CONFLICT)
                return {"id": row.id, "status": row.status, "unchanged": True}
            row.status = "RESOLVED"
            row.resolved_at = now()
            row.resolution_note = command.note
            row.resolved_by = actor.subject
            return {"id": row.id, "status": row.status, "unchanged": False}

    def retry(self, actor: Actor, event_id: str) -> dict[str, Any]:
        with SqlAlchemyUnitOfWork(self.factory) as uow:
            row = uow.session.scalar(
                select(ChangeOutbox)
                .where(ChangeOutbox.event_id == event_id, ChangeOutbox.owner_id == owner_id(actor))
                .with_for_update()
            )
            if row is None:
                raise fail("CHANGE_NOT_FOUND", ErrorCategory.NOT_FOUND)
            if row.status != "FAILED":
                raise fail("CHANGE_NOT_FAILED", ErrorCategory.CONFLICT)
            row.status = "PENDING"
            row.available_at = now()
            row.error_code = None
            row.retry_limit = row.attempts + 5
            return {"event_id": event_id, "status": row.status, "attempts": row.attempts}

    @staticmethod
    def review(session: Session, event: ChangeEvent, target_type: str, target_id: str, reason: str) -> None:
        existing = session.scalar(
            select(ChangeReview.id).where(
                ChangeReview.event_id == event.id,
                ChangeReview.target_type == target_type,
                ChangeReview.target_id == target_id,
                ChangeReview.reason == reason,
            )
        )
        if existing is None:
            session.add(
                ChangeReview(
                    id=uid(),
                    owner_id=event.owner_id,
                    event_id=event.id,
                    target_type=target_type,
                    target_id=target_id,
                    reason=reason,
                    status="OPEN",
                    created_at=now(),
                )
            )

    def consume(self, session: Session, event: ChangeEvent) -> None:
        before, after = json.loads(event.before_json or "{}"), json.loads(event.after_json or "{}")
        if event.context_id is None:
            self.review(session, event, event.table_name, event.target_id, "DIRECT_SQL_CHANGE")
            return
        if event.table_name != "vk_item":
            return
        old_revision = before.get("active_revision_id")
        new_revision = after.get("active_revision_id")
        retired = after.get("lifecycle_status") == "RETIRED" and before.get("lifecycle_status") != "RETIRED"
        if old_revision and (old_revision != new_revision or retired):
            claims = session.scalars(
                select(GraphClaim)
                .join(GraphEvidence, GraphEvidence.version_id == GraphClaim.current_version_id)
                .where(
                    GraphClaim.owner_id == event.owner_id,
                    GraphEvidence.owner_id == event.owner_id,
                    GraphEvidence.knowledge_id == event.target_id,
                    GraphEvidence.revision_id == old_revision,
                )
            ).all()
            for claim in claims:
                self.review(
                    session,
                    event,
                    "vk_g_claim",
                    claim.id,
                    "SOURCE_RETIRED" if retired else "SOURCE_REVISION_CHANGED",
                )
        if new_revision and new_revision != old_revision:
            item = session.scalar(
                select(Item)
                .where(Item.id == event.target_id, Item.owner_id == event.owner_id)
                .with_for_update()
            )
            if item is None or item.active_revision_id != new_revision or item.lifecycle_status != "ACTIVE":
                return
            revision = session.get(Revision, new_revision)
            if revision is None or revision.owner_id != event.owner_id or not revision.content_text:
                return
            if not revision.summary_text:
                revision.summary_text = extract_summary(revision.content_text)
                revision.summary_kind = "EXTRACTIVE"
            navigation_rdf.store(
                session,
                event.owner_id,
                revision.id,
                navigation_rdf.revision_rows(revision, item.scope, item.memory_kind),
                self.rdf_enabled,
            )

    def process_one(self) -> bool:
        with SqlAlchemyUnitOfWork(self.factory, read_only=True) as uow:
            candidates = list(
                uow.session.execute(
                    select(ChangeOutbox.event_id, ChangeOutbox.owner_id)
                    .where(ChangeOutbox.status == "PENDING", ChangeOutbox.available_at <= now())
                    .order_by(ChangeOutbox.available_at, ChangeOutbox.event_id)
                    .limit(10)
                )
            )
        for event_id, owner in candidates:
            try:
                with audited_uow(self.factory, None, "CHANGE_DERIVED_REFRESH", owner=owner) as uow:
                    row = uow.session.scalar(
                        select(ChangeOutbox)
                        .where(
                            ChangeOutbox.event_id == event_id,
                            ChangeOutbox.status == "PENDING",
                            ChangeOutbox.available_at <= now(),
                        )
                        .with_for_update(skip_locked=True)
                    )
                    if row is None:
                        continue
                    # Conditional write also serializes consumers on SQLite, whose SELECT FOR UPDATE is a no-op.
                    claimed: Any = uow.session.execute(
                        update(ChangeOutbox)
                        .where(ChangeOutbox.event_id == event_id, ChangeOutbox.status == "PENDING")
                        .values(status="PROCESSING")
                    )
                    if claimed.rowcount != 1:
                        continue
                    event = uow.session.get(ChangeEvent, event_id)
                    assert event is not None
                    self.consume(uow.session, event)
                    row.status = "DONE"
                    row.attempts += 1
                    row.processed_at = now()
                    row.error_code = None
                return True
            except Exception as error:
                logging.getLogger("python_foundation.worker").error(
                    "Change processing failed type=%s event=%s", type(error).__name__, event_id
                )
                with SqlAlchemyUnitOfWork(self.factory) as uow:
                    row = uow.session.scalar(
                        select(ChangeOutbox)
                        .where(ChangeOutbox.event_id == event_id, ChangeOutbox.status == "PENDING")
                        .with_for_update()
                    )
                    if row:
                        row.attempts += 1
                        row.error_code = "CHANGE_PROCESSING_FAILED"
                        row.status = "FAILED" if row.attempts >= row.retry_limit else "PENDING"
                        row.available_at = now() + timedelta(seconds=min(300, 2 ** min(row.attempts, 8)))
                return True
        return False
