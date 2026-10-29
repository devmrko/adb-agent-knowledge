"""Transactional row history, attribution, outbox and evidence review queue."""

import sqlalchemy as sa
from alembic import op

from knowledge_app.audit_schema_v8 import install, tables

revision = "vk0008"
down_revision = "vk0007"
branch_labels = None
depends_on = None


def upgrade():
    schema = tables(sa.MetaData())
    for table in schema.values():
        table.create(op.get_bind(), checkfirst=True)
    install(op.get_bind())


def downgrade():
    raise RuntimeError("Change history is retained; use an explicitly reviewed retention migration")
