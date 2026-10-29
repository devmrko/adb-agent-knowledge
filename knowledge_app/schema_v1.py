# Frozen v1 schema: do not edit after migration release.
import array
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKeyConstraint, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.dialects.oracle import VECTOR, VectorStorageFormat
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (
        UniqueConstraint("owner_id", "id"),
        ForeignKeyConstraint(
            ["owner_id", "active_revision_id"],
            ["vk_revision.owner_id", "vk_revision.id"],
            name="vk_item_active_fk",
            use_alter=True,
        ),
    )


class Revision(Base):
    __tablename__ = "vk_revision"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(String(64))
    item_id: Mapped[str] = mapped_column(String(36), index=True)
    content_text: Mapped[str | None] = mapped_column(Text)
    summary_text: Mapped[str | None] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(10))
    source_url: Mapped[str | None] = mapped_column(String(2000))
    filename: Mapped[str | None] = mapped_column(String(300))
    mime_type: Mapped[str] = mapped_column(String(100))
    original_data: Mapped[bytes | None] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (
        UniqueConstraint("owner_id", "id"),
        ForeignKeyConstraint(["owner_id", "item_id"], ["vk_item.owner_id", "vk_item.id"]),
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


metadata = Base.metadata
