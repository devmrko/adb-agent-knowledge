"""Durable graph extraction and source-backed review candidates."""

import sqlalchemy as sa
from alembic import op

from knowledge_app.graph_auto_schema_v9 import tables

revision = "vk0009"
down_revision = "vk0008"
branch_labels = None
depends_on = None


def upgrade():
    for table in tables(sa.MetaData()).values():
        table.create(op.get_bind(), checkfirst=True)


def downgrade():
    raise RuntimeError("Extraction and review history is retained")
