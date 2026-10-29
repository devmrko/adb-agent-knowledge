"""Frozen vk0010 schema for agent review and evidenced identity bindings."""

from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.oracle import TIMESTAMP


def tables(metadata: sa.MetaData) -> dict[str, sa.Table]:
    timestamp = sa.DateTime(timezone=True).with_variant(TIMESTAMP(timezone=True), "oracle")

    def c(name: str, kind: Any, nullable: bool = False, **kw: Any) -> sa.Column[Any]:
        return sa.Column(name, kind, nullable=nullable, **kw)

    review = sa.Table(
        "vk_g_review",
        metadata,
        c("id", sa.String(36), primary_key=True),
        c("owner_id", sa.String(64), index=True),
        c("item_id", sa.String(36)),
        c("revision_id", sa.String(36), unique=True),
        c("version", sa.Integer),
        c("status", sa.String(20)),
        c("outcome", sa.String(20), True),
        c("note", sa.String(1000)),
        c("updated_at", timestamp),
    )
    identity = sa.Table(
        "vk_g_identity",
        metadata,
        c("id", sa.String(36), primary_key=True),
        c("owner_id", sa.String(64), index=True),
        c("scope", sa.String(108)),
        c("binding_key", sa.String(64), unique=True),
        c("entity_id", sa.String(36)),
        c("kind", sa.String(16)),
        c("namespace", sa.String(40)),
        c("value", sa.String(500)),
        c("version", sa.Integer),
        c("status", sa.String(16)),
        c("item_id", sa.String(36)),
        c("revision_id", sa.String(36)),
        c("quote", sa.Text),
        c("note", sa.String(1000)),
        c("updated_at", timestamp),
    )
    event = sa.Table(
        "vk_g_operation",
        metadata,
        c("id", sa.String(36), primary_key=True),
        c("owner_id", sa.String(64), index=True),
        c("target_id", sa.String(36), index=True),
        c("kind", sa.String(16)),
        c("version", sa.Integer),
        c("actor", sa.String(500)),
        c("snapshot_json", sa.Text),
        c("created_at", timestamp),
        sa.UniqueConstraint("target_id", "version", name="vk_g_op_version_uq"),
    )
    return {t.name: t for t in (review, identity, event)}
