from datetime import datetime

from sqlalchemy.orm import Mapped

from knowledge_app.graph_ops_schema_v10 import tables
from knowledge_app.models import Base

_schema = tables(Base.metadata)


class GraphReview(Base):
    __table__ = _schema["vk_g_review"]
    id: Mapped[str]
    owner_id: Mapped[str]
    item_id: Mapped[str]
    revision_id: Mapped[str]
    version: Mapped[int]
    status: Mapped[str]
    outcome: Mapped[str | None]
    note: Mapped[str]
    updated_at: Mapped[datetime]


class GraphIdentity(Base):
    __table__ = _schema["vk_g_identity"]
    id: Mapped[str]
    owner_id: Mapped[str]
    scope: Mapped[str]
    binding_key: Mapped[str]
    entity_id: Mapped[str]
    kind: Mapped[str]
    namespace: Mapped[str]
    value: Mapped[str]
    version: Mapped[int]
    status: Mapped[str]
    item_id: Mapped[str]
    revision_id: Mapped[str]
    quote: Mapped[str]
    note: Mapped[str]
    updated_at: Mapped[datetime]


class GraphOperation(Base):
    __table__ = _schema["vk_g_operation"]
    id: Mapped[str]
    owner_id: Mapped[str]
    target_id: Mapped[str]
    kind: Mapped[str]
    version: Mapped[int]
    actor: Mapped[str]
    snapshot_json: Mapped[str]
    created_at: Mapped[datetime]
