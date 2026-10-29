"""Initial knowledge schema. Frozen table definitions for reproducible migrations."""

from alembic import op

from knowledge_app.schema_v1 import metadata

revision = "vk0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    metadata.create_all(op.get_bind(), checkfirst=False)


def downgrade():
    metadata.drop_all(op.get_bind(), checkfirst=False)
