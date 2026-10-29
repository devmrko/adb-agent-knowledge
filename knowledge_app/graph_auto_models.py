from datetime import datetime

from sqlalchemy.orm import Mapped

from knowledge_app.graph_auto_schema_v9 import tables
from knowledge_app.models import Base

_schema = tables(Base.metadata)


class ExtractionRun(Base):
    __table__ = _schema["vk_g_extract"]
    id: Mapped[str]
    owner_id: Mapped[str]
    item_id: Mapped[str]
    revision_id: Mapped[str]
    run_key: Mapped[str]
    schema_version: Mapped[str]
    model: Mapped[str]
    status: Mapped[str]
    attempts: Mapped[int]
    retry_limit: Mapped[int]
    force_extract: Mapped[int]
    lease_token: Mapped[str | None]
    available_at: Mapped[datetime]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    route_json: Mapped[str | None]
    error_code: Mapped[str | None]


class GraphProposal(Base):
    __table__ = _schema["vk_g_proposal"]
    id: Mapped[str]
    owner_id: Mapped[str]
    run_id: Mapped[str]
    item_id: Mapped[str]
    revision_id: Mapped[str]
    scope: Mapped[str]
    candidate_key: Mapped[str]
    payload_json: Mapped[str]
    status: Mapped[str]
    created_at: Mapped[datetime]
    reviewed_at: Mapped[datetime | None]
    reviewed_by: Mapped[str | None]
    review_note: Mapped[str | None]
    resolution_json: Mapped[str | None]
    assertion_id: Mapped[str | None]
    version_id: Mapped[str | None]
