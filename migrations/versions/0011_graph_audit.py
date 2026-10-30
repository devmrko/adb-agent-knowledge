"""Initialize row audit and append-only protection for newer graph tables."""

from alembic import op

from knowledge_app.audit_schema_v11 import install

revision = "vk0011"
down_revision = "vk0010"
branch_labels = None
depends_on = None


def upgrade():
    install(op.get_bind())


def downgrade():
    raise RuntimeError("Graph audit history is retained; use a reviewed retention migration")
