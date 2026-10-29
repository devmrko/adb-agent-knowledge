"""Track declared editing source without relabelling old revisions."""

import sqlalchemy as sa
from alembic import op

revision = "vk0004"
down_revision = "vk0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("vk_revision", sa.Column("edit_origin", sa.String(16), nullable=True))


def downgrade():
    raise RuntimeError("Edit provenance is retained; downgrade is not supported")
