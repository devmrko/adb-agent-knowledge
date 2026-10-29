"""Revision summaries, index documents, memberships and structural RDF manifests."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.oracle import TIMESTAMP

revision = "vk0007"
down_revision = "vk0006"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("vk_revision", sa.Column("summary_kind", sa.String(16), nullable=True))
    op.create_table(
        "vk_index",
        sa.Column("id", sa.String(36), nullable=False, primary_key=True),
        sa.Column("owner_id", sa.String(64), nullable=False, primary_key=False),
        sa.Column("scope", sa.String(108), nullable=False, primary_key=False),
        sa.Column("key", sa.String(120), nullable=False, primary_key=False),
        sa.Column("key_hash", sa.String(64), nullable=False, primary_key=False),
        sa.Column("title", sa.String(200), nullable=False, primary_key=False),
        sa.Column("summary", sa.String(1000), nullable=False, primary_key=False),
        sa.Column("body", sa.Text(), nullable=True, primary_key=False),
        sa.Column("version", sa.Integer(), nullable=False, primary_key=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True).with_variant(TIMESTAMP(timezone=True), "oracle"),
            nullable=False,
            primary_key=False,
        ),
        sa.UniqueConstraint(*["owner_id", "id"]),
        sa.UniqueConstraint(*["key_hash"]),
    )
    op.create_index("ix_vk_index_owner_id", "vk_index", ["owner_id"], unique=False)
    op.create_index("ix_vk_index_scope", "vk_index", ["scope"], unique=False)
    op.create_table(
        "vk_index_entry",
        sa.Column("id", sa.String(36), nullable=False, primary_key=True),
        sa.Column("owner_id", sa.String(64), nullable=False, primary_key=False),
        sa.Column("index_id", sa.String(36), nullable=False, primary_key=False),
        sa.Column("item_id", sa.String(36), nullable=False, primary_key=False),
        sa.Column("section", sa.String(120), nullable=False, primary_key=False),
        sa.Column("position", sa.Integer(), nullable=False, primary_key=False),
        sa.Column("note", sa.String(300), nullable=True, primary_key=False),
        sa.UniqueConstraint(*["index_id", "item_id"]),
        sa.ForeignKeyConstraint(["owner_id", "index_id"], ["vk_index.owner_id", "vk_index.id"]),
        sa.ForeignKeyConstraint(["owner_id", "item_id"], ["vk_item.owner_id", "vk_item.id"]),
    )
    op.create_index("ix_vk_index_entry_index_id", "vk_index_entry", ["index_id"], unique=False)
    op.create_index("ix_vk_index_entry_item_id", "vk_index_entry", ["item_id"], unique=False)
    op.create_index("ix_vk_index_entry_owner_id", "vk_index_entry", ["owner_id"], unique=False)
    op.create_table(
        "vk_index_change",
        sa.Column("id", sa.String(36), nullable=False, primary_key=True),
        sa.Column("owner_id", sa.String(64), nullable=False, primary_key=False),
        sa.Column("index_id", sa.String(36), nullable=False, primary_key=False),
        sa.Column("version", sa.Integer(), nullable=False, primary_key=False),
        sa.Column("payload_json", sa.Text(), nullable=False, primary_key=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True).with_variant(TIMESTAMP(timezone=True), "oracle"),
            nullable=False,
            primary_key=False,
        ),
        sa.UniqueConstraint(*["index_id", "version"]),
        sa.ForeignKeyConstraint(["owner_id", "index_id"], ["vk_index.owner_id", "vk_index.id"]),
    )
    op.create_index("ix_vk_index_change_index_id", "vk_index_change", ["index_id"], unique=False)
    op.create_table(
        "vk_nav_snapshot",
        sa.Column("id", sa.String(36), nullable=False, primary_key=True),
        sa.Column("owner_id", sa.String(64), nullable=False, primary_key=False),
        sa.Column("payload_json", sa.Text(), nullable=False, primary_key=False),
        sa.Column("native_stored", sa.Integer(), nullable=False, primary_key=False),
    )
    op.create_index("ix_vk_nav_snapshot_owner_id", "vk_nav_snapshot", ["owner_id"], unique=False)


def downgrade():
    raise RuntimeError("Index history and source summaries are retained")
