"""Exact source evidence for SDK memories; SDK content remains in its own store."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKeyConstraint, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from knowledge_app.models import Base, now


class MemoryEvidence(Base):
    __tablename__ = "vk_memory_evidence"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    memory_id: Mapped[str] = mapped_column(String(128), index=True)
    knowledge_id: Mapped[str] = mapped_column(String(36), index=True)
    revision_id: Mapped[str] = mapped_column(String(36))
    quote: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (
        ForeignKeyConstraint(["owner_id", "knowledge_id"], ["vk_item.owner_id", "vk_item.id"]),
        ForeignKeyConstraint(["owner_id", "revision_id"], ["vk_revision.owner_id", "vk_revision.id"]),
    )
