"""Owner-approved principles and immutable application revisions."""

import sqlalchemy as sa
from alembic import op

revision = "vk0014"
down_revision = "vk0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vk_principle_bundle",
        sa.Column("owner_id", sa.String(64), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("rules_json", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "vk_principle_revision",
        sa.Column("owner_id", sa.String(64), primary_key=True),
        sa.Column("version", sa.Integer(), primary_key=True),
        sa.Column("rules_json", sa.Text(), nullable=False),
        sa.Column("change_note", sa.String(500), nullable=False),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("vk_principle_revision")
    op.drop_table("vk_principle_bundle")
