"""Persist stable SDK keys for indexed primary-source joins."""

import hashlib
import json

import sqlalchemy as sa
from alembic import op

revision = "vk0016"
down_revision = "vk0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("vk_source_transfer", sa.Column("sdk_record_id", sa.String(64), nullable=True))
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT owner_id, knowledge_id, revision_id FROM vk_source_transfer")).all()
    for owner, kid, rid in rows:
        key = hashlib.sha256(json.dumps([owner, kid, rid]).encode()).hexdigest()
        bind.execute(
            sa.text(
                "UPDATE vk_source_transfer SET sdk_record_id=:key WHERE owner_id=:owner AND revision_id=:rid"
            ),
            {"key": key, "owner": owner, "rid": rid},
        )
    with op.batch_alter_table("vk_source_transfer") as batch:
        batch.alter_column("sdk_record_id", existing_type=sa.String(64), nullable=False)
        batch.create_index("ix_vk_source_sdk_key", ["sdk_record_id"], unique=True)


def downgrade() -> None:
    with op.batch_alter_table("vk_source_transfer") as batch:
        batch.drop_index("ix_vk_source_sdk_key")
        batch.drop_column("sdk_record_id")
