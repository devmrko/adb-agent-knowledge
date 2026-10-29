"""Memory scope, lifecycle and request deduplication. Additive migration."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.oracle import TIMESTAMP

revision = "vk0002"
down_revision = "vk0001"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("vk_item") as batch:
        for name, length, default in [
            ("memory_kind", 20, "DOCUMENT"),
            ("scope", 108, "global"),
            ("lifecycle_status", 16, "ACTIVE"),
        ]:
            batch.add_column(sa.Column(name, sa.String(length), server_default=default, nullable=False))
        for name, length in [
            ("superseded_by_id", 36),
            ("idempotency_key", 100),
            ("request_digest", 64),
            ("request_key_hash", 64),
        ]:
            batch.add_column(sa.Column(name, sa.String(length), nullable=True))
        batch.add_column(sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_index("ix_vk_item_scope", ["scope"])
        batch.create_unique_constraint("vk_item_request_uq", ["request_key_hash"])
        batch.create_foreign_key(
            "vk_item_superseded_fk", "vk_item", ["owner_id", "superseded_by_id"], ["owner_id", "id"]
        )
    with op.batch_alter_table("vk_revision") as batch:
        batch.add_column(sa.Column("revision_no", sa.Integer(), server_default="1", nullable=False))
        batch.add_column(sa.Column("change_note", sa.String(500), nullable=True))
        batch.create_unique_constraint("vk_revision_no_uq", ["item_id", "revision_no"])
    op.add_column("vk_chunk", sa.Column("source_part", sa.String(16), nullable=True))
    op.create_table(
        "vk_event",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(64), nullable=False),
        sa.Column("item_id", sa.String(36), nullable=False),
        sa.Column("event_type", sa.String(20), nullable=False),
        sa.Column("revision_id", sa.String(36), nullable=True),
        sa.Column("related_item_id", sa.String(36), nullable=True),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True).with_variant(TIMESTAMP(timezone=True), "oracle"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "item_id"], ["vk_item.owner_id", "vk_item.id"], name="vk_event_item_fk"
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "revision_id"],
            ["vk_revision.owner_id", "vk_revision.id"],
            name="vk_event_revision_fk",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "related_item_id"], ["vk_item.owner_id", "vk_item.id"], name="vk_event_related_fk"
        ),
    )
    op.create_index("ix_vk_event_item_id", "vk_event", ["item_id"])


def downgrade():
    # Dropping immutable memory history is intentionally not an automatic operation.
    raise RuntimeError("Memory lifecycle migration requires a reviewed backup/restore plan to downgrade")
