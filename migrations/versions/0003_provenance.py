"""Revision-level client machine identity and source locations."""

import sqlalchemy as sa
from alembic import op

revision = "vk0003"
down_revision = "vk0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("vk_revision", sa.Column("origin_machine_id", sa.String(100), nullable=True))
    op.add_column("vk_revision", sa.Column("origin_machine_label", sa.String(120), nullable=True))
    op.add_column("vk_revision", sa.Column("sources_json", sa.Text(), nullable=True))


def downgrade():
    raise RuntimeError("Provenance history is retained; downgrade is not supported")
