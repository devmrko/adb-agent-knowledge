from datetime import datetime
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped

from knowledge_app import audit_schema_v8
from knowledge_app.models import Base

_schema = audit_schema_v8.tables(Base.metadata)


class ChangeContext(Base):
    __table__ = _schema["vk_change_context"]
    id: Mapped[str]
    owner_id: Mapped[str]
    transaction_id: Mapped[str | None]
    operation: Mapped[str]
    request_id: Mapped[str]
    actor_subject: Mapped[str | None]
    actor_issuer: Mapped[str | None]
    machine_id: Mapped[str | None]
    edit_origin: Mapped[str | None]
    reason: Mapped[str | None]
    source: Mapped[str]
    created_at: Mapped[datetime]


class ChangeEvent(Base):
    __table__ = _schema["vk_change_event"]
    id: Mapped[str]
    owner_id: Mapped[str]
    context_id: Mapped[str | None]
    table_name: Mapped[str]
    target_id: Mapped[str]
    action: Mapped[str]
    before_json: Mapped[str | None]
    after_json: Mapped[str | None]
    db_user: Mapped[str | None]
    created_at: Mapped[datetime]


class ChangeOutbox(Base):
    __table__ = _schema["vk_change_outbox"]
    event_id: Mapped[str]
    owner_id: Mapped[str]
    status: Mapped[str]
    attempts: Mapped[int]
    retry_limit: Mapped[int]
    available_at: Mapped[datetime]
    processed_at: Mapped[datetime | None]
    error_code: Mapped[str | None]


class ChangeReview(Base):
    __table__ = _schema["vk_change_review"]
    id: Mapped[str]
    owner_id: Mapped[str]
    event_id: Mapped[str]
    target_type: Mapped[str]
    target_id: Mapped[str]
    reason: Mapped[str]
    status: Mapped[str]
    created_at: Mapped[datetime]
    resolved_at: Mapped[datetime | None]
    resolution_note: Mapped[str | None]
    resolved_by: Mapped[str | None]


@event.listens_for(Base.metadata, "after_create")
def install_audit(target: Any, connection: Connection, **kw: Any) -> None:
    audit_schema_v8.install(connection)
