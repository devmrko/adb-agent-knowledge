"""Durable per-revision v3 source transfer manifest; no automatic migration."""

import sqlalchemy as sa
from alembic import op

revision = "vk0015"
down_revision = "vk0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vk_source_transfer",
        sa.Column("owner_id", sa.String(64), primary_key=True),
        sa.Column("revision_id", sa.String(36), primary_key=True),
        sa.Column("knowledge_id", sa.String(36), nullable=False),
        sa.Column("store_id", sa.String(16), nullable=False),
        sa.Column("profile_id", sa.String(64), nullable=False),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("lease_token", sa.String(36)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(64)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id", "revision_id"], ["vk_revision.owner_id", "vk_revision.id"]),
        sa.ForeignKeyConstraint(["owner_id", "knowledge_id"], ["vk_item.owner_id", "vk_item.id"]),
    )


def downgrade() -> None:
    op.drop_table("vk_source_transfer")
