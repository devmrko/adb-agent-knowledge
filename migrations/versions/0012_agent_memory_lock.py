"""Serialize SDK profile/idempotent writes per authenticated owner."""

import sqlalchemy as sa
from alembic import op

revision = "vk0012"
down_revision = "vk0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("vk_memory_lock", sa.Column("owner_id", sa.String(64), primary_key=True))


def downgrade() -> None:
    op.drop_table("vk_memory_lock")
