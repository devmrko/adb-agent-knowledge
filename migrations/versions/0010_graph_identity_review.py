"""Source-version review and evidence-backed entity identity."""

import sqlalchemy as sa
from alembic import op

from knowledge_app.graph_ops_schema_v10 import tables

revision = "vk0010"
down_revision = "vk0009"
branch_labels = None
depends_on = None


def upgrade():
    for table in tables(sa.MetaData()).values():
        table.create(op.get_bind(), checkfirst=True)


def downgrade():
    raise RuntimeError("Identity and review history is retained")
