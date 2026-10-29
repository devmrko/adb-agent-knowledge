from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from knowledge_app import schema_v1


def test_additive_migration_preserves_existing_source(tmp_path, monkeypatch):
    db_url = "sqlite:///" + str(tmp_path / "migration.db")
    monkeypatch.setenv("DATABASE_URL", db_url)
    config = Config("alembic.ini")
    command.upgrade(config, "vk0001")
    engine = create_engine(db_url)
    with Session(engine) as session, session.begin():
        item = schema_v1.Item(owner_id="existing-user", title="기존 Oracle 문서", knowledge_type="NOTE")
        session.add(item)
        session.flush()
        revision = schema_v1.Revision(
            owner_id=item.owner_id,
            item_id=item.id,
            source_type="TEXT",
            mime_type="text/plain",
            content_text="원문 보존",
        )
        session.add(revision)
        session.flush()
        item.active_revision_id = revision.id
        item_id = item.id
    command.upgrade(config, "head")
    with engine.connect() as con:
        assert con.scalar(text("select version_num from vk_alembic_version")) == "vk0009"
        row = con.execute(
            text("select memory_kind, scope, lifecycle_status from vk_item where id=:id"), dict(id=item_id)
        ).one()
        assert tuple(row) == ("DOCUMENT", "global", "ACTIVE")
        assert con.scalar(text("select edit_origin from vk_revision")) is None
        assert con.scalar(text("select content_text from vk_revision")) == "원문 보존"
        assert con.exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []
    assert "vk_event" in inspect(engine).get_table_names()
    assert {"origin_machine_id", "origin_machine_label", "sources_json"} <= {
        c["name"] for c in inspect(engine).get_columns("vk_revision")
    }
    engine.dispose()
