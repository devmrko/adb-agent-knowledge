"""Shared bitemporal graph indexes and source evidence."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.oracle import TIMESTAMP

revision = "vk0006"
down_revision = "vk0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "vk_g_entity",
        sa.Column("id", sa.String(36), nullable=False, primary_key=True),
        sa.Column("owner_id", sa.String(64), nullable=False, primary_key=False),
        sa.Column("scope", sa.String(108), nullable=False, primary_key=False),
        sa.Column("identity_hash", sa.String(64), nullable=False, primary_key=False),
        sa.Column("identity_key", sa.String(200), nullable=False, primary_key=False),
        sa.Column("label", sa.String(200), nullable=False, primary_key=False),
        sa.Column("kind", sa.String(40), nullable=False, primary_key=False),
        sa.Column("aliases_json", sa.Text(), nullable=False, primary_key=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True).with_variant(TIMESTAMP(timezone=True), "oracle"),
            nullable=False,
            primary_key=False,
        ),
        sa.UniqueConstraint("identity_hash"),
        sa.UniqueConstraint("owner_id", "id"),
    )
    op.create_index("ix_vk_g_entity_scope", "vk_g_entity", ["scope"], unique=False)
    op.create_index("ix_vk_g_entity_owner_id", "vk_g_entity", ["owner_id"], unique=False)
    op.create_table(
        "vk_g_claim",
        sa.Column("id", sa.String(36), nullable=False, primary_key=True),
        sa.Column("owner_id", sa.String(64), nullable=False, primary_key=False),
        sa.Column("scope", sa.String(108), nullable=False, primary_key=False),
        sa.Column("signature", sa.String(64), nullable=False, primary_key=False),
        sa.Column("current_version_id", sa.String(36), nullable=True, primary_key=False),
        sa.UniqueConstraint("signature"),
        sa.UniqueConstraint("owner_id", "id"),
    )
    op.create_index("ix_vk_g_claim_scope", "vk_g_claim", ["scope"], unique=False)
    op.create_index("ix_vk_g_claim_owner_id", "vk_g_claim", ["owner_id"], unique=False)
    op.create_table(
        "vk_g_version",
        sa.Column("id", sa.String(36), nullable=False, primary_key=True),
        sa.Column("owner_id", sa.String(64), nullable=False, primary_key=False),
        sa.Column("claim_id", sa.String(36), nullable=False, primary_key=False),
        sa.Column("scope", sa.String(108), nullable=False, primary_key=False),
        sa.Column("subject_id", sa.String(36), nullable=False, primary_key=False),
        sa.Column("object_id", sa.String(36), nullable=True, primary_key=False),
        sa.Column("predicate", sa.String(40), nullable=False, primary_key=False),
        sa.Column("temporal_kind", sa.String(16), nullable=False, primary_key=False),
        sa.Column(
            "valid_from",
            sa.DateTime(timezone=True).with_variant(TIMESTAMP(timezone=True), "oracle"),
            nullable=True,
            primary_key=False,
        ),
        sa.Column(
            "valid_to",
            sa.DateTime(timezone=True).with_variant(TIMESTAMP(timezone=True), "oracle"),
            nullable=True,
            primary_key=False,
        ),
        sa.Column(
            "recorded_from",
            sa.DateTime(timezone=True).with_variant(TIMESTAMP(timezone=True), "oracle"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column(
            "recorded_to",
            sa.DateTime(timezone=True).with_variant(TIMESTAMP(timezone=True), "oracle"),
            nullable=True,
            primary_key=False,
        ),
        sa.Column("status", sa.String(16), nullable=False, primary_key=False),
        sa.Column("payload_json", sa.Text(), nullable=False, primary_key=False),
        sa.ForeignKeyConstraint(["owner_id", "claim_id"], ["vk_g_claim.owner_id", "vk_g_claim.id"]),
        sa.ForeignKeyConstraint(["owner_id", "subject_id"], ["vk_g_entity.owner_id", "vk_g_entity.id"]),
        sa.UniqueConstraint("owner_id", "id"),
        sa.ForeignKeyConstraint(["owner_id", "object_id"], ["vk_g_entity.owner_id", "vk_g_entity.id"]),
    )
    op.create_index("ix_vk_g_version_owner_id", "vk_g_version", ["owner_id"], unique=False)
    op.create_index("ix_vk_g_version_claim_id", "vk_g_version", ["claim_id"], unique=False)
    op.create_index("ix_vk_g_version_object_id", "vk_g_version", ["object_id"], unique=False)
    op.create_index("ix_vk_g_version_scope", "vk_g_version", ["scope"], unique=False)
    op.create_index("ix_vk_g_version_subject_id", "vk_g_version", ["subject_id"], unique=False)
    op.create_index("ix_vk_g_version_recorded_from", "vk_g_version", ["recorded_from"], unique=False)
    op.create_table(
        "vk_g_evidence",
        sa.Column("id", sa.String(36), nullable=False, primary_key=True),
        sa.Column("owner_id", sa.String(64), nullable=False, primary_key=False),
        sa.Column("version_id", sa.String(36), nullable=False, primary_key=False),
        sa.Column("knowledge_id", sa.String(36), nullable=False, primary_key=False),
        sa.Column("revision_id", sa.String(36), nullable=False, primary_key=False),
        sa.Column("quote", sa.Text(), nullable=False, primary_key=False),
        sa.ForeignKeyConstraint(["owner_id", "version_id"], ["vk_g_version.owner_id", "vk_g_version.id"]),
        sa.ForeignKeyConstraint(["owner_id", "revision_id"], ["vk_revision.owner_id", "vk_revision.id"]),
        sa.ForeignKeyConstraint(["owner_id", "knowledge_id"], ["vk_item.owner_id", "vk_item.id"]),
    )
    op.create_index("ix_vk_g_evidence_knowledge_id", "vk_g_evidence", ["knowledge_id"], unique=False)
    op.create_index("ix_vk_g_evidence_version_id", "vk_g_evidence", ["version_id"], unique=False)
    op.create_index("ix_vk_g_evidence_revision_id", "vk_g_evidence", ["revision_id"], unique=False)


def downgrade():
    raise RuntimeError("Shared graph history is retained; downgrade is not supported")
