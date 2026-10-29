import array
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKeyConstraint, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.dialects.oracle import TIMESTAMP, VECTOR, VectorStorageFormat
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator, TypeEngine


def uid() -> str:
    return str(uuid.uuid4())


def now() -> datetime:
    return datetime.now(UTC)


class Vector(TypeDecorator[list[float]]):
    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "oracle":
            return dialect.type_descriptor(VECTOR(1024, VectorStorageFormat.FLOAT32))  # type: ignore[no-untyped-call]
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value: list[float] | None, dialect: Dialect) -> Any:
        if value is None:
            return None
        return array.array("f", value) if dialect.name == "oracle" else json.dumps(value)

    def process_result_value(self, value: Any, dialect: Dialect) -> list[float] | None:
        if value is None:
            return None
        return list(value) if dialect.name == "oracle" else list(json.loads(value))


class Base(DeclarativeBase):
    pass


class Item(Base):
    __tablename__ = "vk_item"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(300))
    knowledge_type: Mapped[str] = mapped_column(String(40))
    category: Mapped[str | None] = mapped_column(String(120))
    tags_json: Mapped[str] = mapped_column(Text, default="[]")
    active_revision_id: Mapped[str | None] = mapped_column(String(36))
    idempotency_key: Mapped[str | None] = mapped_column(String(100))
    request_key_hash: Mapped[str | None] = mapped_column(String(64))
    request_digest: Mapped[str | None] = mapped_column(String(64))
    memory_kind: Mapped[str] = mapped_column(String(20), default="DOCUMENT", server_default="DOCUMENT")
    scope: Mapped[str] = mapped_column(String(108), default="global", server_default="global", index=True)
    lifecycle_status: Mapped[str] = mapped_column(String(16), default="ACTIVE", server_default="ACTIVE")
    superseded_by_id: Mapped[str | None] = mapped_column(String(36))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    __table_args__ = (
        UniqueConstraint("owner_id", "id"),
        UniqueConstraint("request_key_hash", name="vk_item_request_uq"),
        ForeignKeyConstraint(
            ["owner_id", "active_revision_id"],
            ["vk_revision.owner_id", "vk_revision.id"],
            name="vk_item_active_fk",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["owner_id", "superseded_by_id"],
            ["vk_item.owner_id", "vk_item.id"],
            name="vk_item_superseded_fk",
        ),
    )


class Revision(Base):
    __tablename__ = "vk_revision"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(String(64))
    item_id: Mapped[str] = mapped_column(String(36), index=True)
    revision_no: Mapped[int] = mapped_column(default=1, server_default="1")
    change_note: Mapped[str | None] = mapped_column(String(500))
    edit_origin: Mapped[str | None] = mapped_column(String(16))
    origin_machine_id: Mapped[str | None] = mapped_column(String(100))
    origin_machine_label: Mapped[str | None] = mapped_column(String(120))
    sources_json: Mapped[str | None] = mapped_column(Text)
    content_text: Mapped[str | None] = mapped_column(Text)
    summary_text: Mapped[str | None] = mapped_column(Text)
    summary_kind: Mapped[str | None] = mapped_column(String(16))
    source_type: Mapped[str] = mapped_column(String(10))
    source_url: Mapped[str | None] = mapped_column(String(2000))
    filename: Mapped[str | None] = mapped_column(String(300))
    mime_type: Mapped[str] = mapped_column(String(100))
    original_data: Mapped[bytes | None] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (
        UniqueConstraint("owner_id", "id"),
        UniqueConstraint("item_id", "revision_no", name="vk_revision_no_uq"),
        ForeignKeyConstraint(["owner_id", "item_id"], ["vk_item.owner_id", "vk_item.id"]),
    )


class Event(Base):
    __tablename__ = "vk_event"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(String(64))
    item_id: Mapped[str] = mapped_column(String(36), index=True)
    event_type: Mapped[str] = mapped_column(String(20))
    revision_id: Mapped[str | None] = mapped_column(String(36))
    related_item_id: Mapped[str | None] = mapped_column(String(36))
    reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True).with_variant(TIMESTAMP(timezone=True), "oracle"), default=now
    )
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "item_id"], ["vk_item.owner_id", "vk_item.id"], name="vk_event_item_fk"
        ),
        ForeignKeyConstraint(
            ["owner_id", "revision_id"],
            ["vk_revision.owner_id", "vk_revision.id"],
            name="vk_event_revision_fk",
        ),
        ForeignKeyConstraint(
            ["owner_id", "related_item_id"], ["vk_item.owner_id", "vk_item.id"], name="vk_event_related_fk"
        ),
    )


class Job(Base):
    __tablename__ = "vk_job"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(String(64))
    revision_id: Mapped[str] = mapped_column(String(36), unique=True)
    status: Mapped[str] = mapped_column(String(16), default="QUEUED", index=True)
    stage: Mapped[str] = mapped_column(String(20), default="WAITING")
    error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        ForeignKeyConstraint(["owner_id", "revision_id"], ["vk_revision.owner_id", "vk_revision.id"]),
    )


class Chunk(Base):
    __tablename__ = "vk_chunk"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    revision_id: Mapped[str] = mapped_column(String(36), index=True)
    source_part: Mapped[str | None] = mapped_column(String(16))
    chunk_no: Mapped[int]
    text: Mapped[str] = mapped_column(Text)
    page_no: Mapped[int]
    char_start: Mapped[int]
    char_end: Mapped[int]
    profile_id: Mapped[str] = mapped_column(String(64), index=True)
    embedding: Mapped[list[float]] = mapped_column(Vector())
    __table_args__ = (
        UniqueConstraint("revision_id", "chunk_no"),
        ForeignKeyConstraint(["owner_id", "revision_id"], ["vk_revision.owner_id", "vk_revision.id"]),
    )


class Workflow(Base):
    __tablename__ = "vk_workflow"
    revision_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64))
    payload_json: Mapped[str] = mapped_column(Text)
    payload_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (
        ForeignKeyConstraint(["owner_id", "revision_id"], ["vk_revision.owner_id", "vk_revision.id"]),
    )


class GraphEntity(Base):
    __tablename__ = "vk_g_entity"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    scope: Mapped[str] = mapped_column(String(108), index=True)
    identity_hash: Mapped[str] = mapped_column(String(64), unique=True)
    identity_key: Mapped[str] = mapped_column(String(200))
    label: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(40))
    aliases_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True).with_variant(TIMESTAMP(timezone=True), "oracle"), default=now
    )
    __table_args__ = (UniqueConstraint("owner_id", "id"),)


class GraphClaim(Base):
    __tablename__ = "vk_g_claim"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    scope: Mapped[str] = mapped_column(String(108), index=True)
    signature: Mapped[str] = mapped_column(String(64), unique=True)
    current_version_id: Mapped[str | None] = mapped_column(String(36))
    __table_args__ = (UniqueConstraint("owner_id", "id"),)


class GraphVersion(Base):
    __tablename__ = "vk_g_version"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    claim_id: Mapped[str] = mapped_column(String(36), index=True)
    scope: Mapped[str] = mapped_column(String(108), index=True)
    subject_id: Mapped[str] = mapped_column(String(36), index=True)
    object_id: Mapped[str | None] = mapped_column(String(36), index=True)
    predicate: Mapped[str] = mapped_column(String(40))
    temporal_kind: Mapped[str] = mapped_column(String(16))
    valid_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True).with_variant(TIMESTAMP(timezone=True), "oracle")
    )
    valid_to: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True).with_variant(TIMESTAMP(timezone=True), "oracle")
    )
    recorded_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True).with_variant(TIMESTAMP(timezone=True), "oracle"), index=True
    )
    recorded_to: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True).with_variant(TIMESTAMP(timezone=True), "oracle")
    )
    status: Mapped[str] = mapped_column(String(16))
    payload_json: Mapped[str] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint("owner_id", "id"),
        ForeignKeyConstraint(["owner_id", "claim_id"], ["vk_g_claim.owner_id", "vk_g_claim.id"]),
        ForeignKeyConstraint(["owner_id", "subject_id"], ["vk_g_entity.owner_id", "vk_g_entity.id"]),
        ForeignKeyConstraint(["owner_id", "object_id"], ["vk_g_entity.owner_id", "vk_g_entity.id"]),
    )


class GraphEvidence(Base):
    __tablename__ = "vk_g_evidence"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(String(64))
    version_id: Mapped[str] = mapped_column(String(36), index=True)
    knowledge_id: Mapped[str] = mapped_column(String(36), index=True)
    revision_id: Mapped[str] = mapped_column(String(36), index=True)
    quote: Mapped[str] = mapped_column(Text)
    __table_args__ = (
        ForeignKeyConstraint(["owner_id", "version_id"], ["vk_g_version.owner_id", "vk_g_version.id"]),
        ForeignKeyConstraint(["owner_id", "revision_id"], ["vk_revision.owner_id", "vk_revision.id"]),
        ForeignKeyConstraint(["owner_id", "knowledge_id"], ["vk_item.owner_id", "vk_item.id"]),
    )


class KnowledgeIndex(Base):
    __tablename__ = "vk_index"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    scope: Mapped[str] = mapped_column(String(108), index=True)
    key: Mapped[str] = mapped_column(String(120))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(String(1000))
    body: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True).with_variant(TIMESTAMP(timezone=True), "oracle"), default=now
    )
    __table_args__ = (UniqueConstraint("owner_id", "id"),)


class IndexEntry(Base):
    __tablename__ = "vk_index_entry"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    index_id: Mapped[str] = mapped_column(String(36), index=True)
    item_id: Mapped[str] = mapped_column(String(36), index=True)
    section: Mapped[str] = mapped_column(String(120), default="일반")
    position: Mapped[int] = mapped_column(default=0)
    note: Mapped[str | None] = mapped_column(String(300))
    __table_args__ = (
        UniqueConstraint("index_id", "item_id"),
        ForeignKeyConstraint(["owner_id", "index_id"], ["vk_index.owner_id", "vk_index.id"]),
        ForeignKeyConstraint(["owner_id", "item_id"], ["vk_item.owner_id", "vk_item.id"]),
    )


class IndexChange(Base):
    __tablename__ = "vk_index_change"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(String(64))
    index_id: Mapped[str] = mapped_column(String(36), index=True)
    version: Mapped[int] = mapped_column()
    payload_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True).with_variant(TIMESTAMP(timezone=True), "oracle"), default=now
    )
    __table_args__ = (
        UniqueConstraint("index_id", "version"),
        ForeignKeyConstraint(["owner_id", "index_id"], ["vk_index.owner_id", "vk_index.id"]),
    )


class NavigationSnapshot(Base):
    __tablename__ = "vk_nav_snapshot"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    payload_json: Mapped[str] = mapped_column(Text)
    native_stored: Mapped[int] = mapped_column(default=0)
