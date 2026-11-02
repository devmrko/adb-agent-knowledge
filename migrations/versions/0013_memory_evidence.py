"""Add exact evidence references without duplicating SDK memories."""

import sqlalchemy as sa
from alembic import op

revision = "vk0013"
down_revision = "vk0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vk_memory_evidence",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("owner_id", sa.String(64), nullable=False),
        sa.Column("memory_id", sa.String(128), nullable=False),
        sa.Column("knowledge_id", sa.String(36), nullable=False),
        sa.Column("revision_id", sa.String(36), nullable=False),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id", "knowledge_id"], ["vk_item.owner_id", "vk_item.id"]),
        sa.ForeignKeyConstraint(["owner_id", "revision_id"], ["vk_revision.owner_id", "vk_revision.id"]),
    )
    for col in ("owner_id", "memory_id", "knowledge_id"):
        op.create_index("ix_vk_memory_evidence_" + col, "vk_memory_evidence", [col])


def downgrade() -> None:
    op.drop_table("vk_memory_evidence")
