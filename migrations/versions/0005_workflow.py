"""Revision-bound workflow manifest. Native RDF setup is a separate explicit step."""

import sqlalchemy as sa
from alembic import op

revision = "vk0005"
down_revision = "vk0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "vk_workflow",
        sa.Column("revision_id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(64), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id", "revision_id"], ["vk_revision.owner_id", "vk_revision.id"]),
    )


def downgrade():
    raise RuntimeError("Workflow history is retained; downgrade is not supported")
