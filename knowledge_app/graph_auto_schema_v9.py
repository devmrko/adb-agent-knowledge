"""Frozen vk0009 schema. Preserve migration semantics."""

from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.oracle import TIMESTAMP


def tables(metadata: sa.MetaData) -> dict[str, sa.Table]:
    timestamp = sa.DateTime(timezone=True).with_variant(TIMESTAMP(timezone=True), "oracle")

    def c(name: str, kind: Any, nullable: bool = False, **kw: Any) -> sa.Column[Any]:
        return sa.Column(name, kind, nullable=nullable, **kw)

    run = sa.Table(
        "vk_g_extract",
        metadata,
        c("id", sa.String(36), primary_key=True),
        c("owner_id", sa.String(64), index=True),
        c("item_id", sa.String(36)),
        c("revision_id", sa.String(36)),
        c("run_key", sa.String(64), unique=True),
        c("schema_version", sa.String(40)),
        c("model", sa.String(200)),
        c("status", sa.String(20), index=True),
        c("attempts", sa.Integer),
        c("retry_limit", sa.Integer),
        c("force_extract", sa.Integer),
        c("lease_token", sa.String(36), True),
        c("available_at", timestamp),
        c("created_at", timestamp),
        c("updated_at", timestamp),
        c("route_json", sa.Text, True),
        c("error_code", sa.String(80), True),
    )
    proposal = sa.Table(
        "vk_g_proposal",
        metadata,
        c("id", sa.String(36), primary_key=True),
        c("owner_id", sa.String(64), index=True),
        c("run_id", sa.String(36), index=True),
        c("item_id", sa.String(36)),
        c("revision_id", sa.String(36)),
        c("scope", sa.String(108)),
        c("candidate_key", sa.String(64), unique=True),
        c("payload_json", sa.Text),
        c("status", sa.String(20), index=True),
        c("created_at", timestamp),
        c("reviewed_at", timestamp, True),
        c("reviewed_by", sa.String(500), True),
        c("review_note", sa.String(1000), True),
        c("resolution_json", sa.Text, True),
        c("assertion_id", sa.String(36), True),
        c("version_id", sa.String(36), True),
    )
    return {t.name: t for t in (run, proposal)}
