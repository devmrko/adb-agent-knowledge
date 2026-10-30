import json
from datetime import UTC, datetime

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import DateTime, Integer, create_engine, func, select, text
from sqlalchemy.exc import IntegrityError

from knowledge_app.audit_schema_v11 import TABLES, install, statements
from knowledge_app.models import Base


def values(name, identifier):
    row = {}
    for column in Base.metadata.tables[name].columns:
        if column.nullable:
            continue
        if isinstance(column.type, DateTime):
            row[column.name] = datetime.now(UTC)
        elif isinstance(column.type, Integer):
            row[column.name] = 1
        else:
            row[column.name] = "{}" if column.name.endswith("_json") else identifier
    row.update(id=identifier, owner_id="owner-a")
    return row


@pytest.mark.parametrize("existing", [False, True])
def test_migration_installs_graph_audit_preserves_rows_and_repeats_safely(tmp_path, monkeypatch, existing):
    url = "sqlite:///" + str(tmp_path / "migration.db")
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config("alembic.ini")
    engine = create_engine(url)
    if existing:
        command.upgrade(config, "vk0010")
        with engine.begin() as con:
            con.execute(Base.metadata.tables["vk_g_review"].insert().values(**values("vk_g_review", "old")))
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    with engine.begin() as con:
        install(con)
        assert con.scalar(text("SELECT version_num FROM vk_alembic_version")) == "vk0011"
        if existing:
            assert con.scalar(text("SELECT id FROM vk_g_review WHERE id='old'")) == "old"
            assert con.scalar(text("SELECT count(*) FROM vk_change_event WHERE target_id='old'")) == 0
        for name in TABLES:
            table = Base.metadata.tables[name]
            identifier = name.removeprefix("vk_g_")
            con.execute(table.insert().values(**values(name, identifier)))
            if name == "vk_g_operation":
                continue
            con.execute(table.update().where(table.c.id == identifier).values(status="UPDATED"))
            con.execute(table.delete().where(table.c.id == identifier))
            events = con.execute(
                text("SELECT action,before_json,after_json FROM vk_change_event WHERE table_name=:name"),
                {"name": name},
            ).all()
            assert {e.action for e in events} == {"INSERT", "UPDATE", "DELETE"}
            updated = next(e for e in events if e.action == "UPDATE")
            assert json.loads(updated.before_json)["status"] == identifier
            assert json.loads(updated.after_json)["status"] == "UPDATED"
            assert "lease_token" not in json.loads(updated.after_json)
        assert con.scalar(text("SELECT count(*) FROM vk_change_event")) == 13
        assert con.scalar(text("SELECT count(*) FROM vk_change_outbox")) == 13
        for sql in (
            "UPDATE vk_g_operation SET actor='tampered'",
            "DELETE FROM vk_g_operation",
        ):
            with pytest.raises(IntegrityError, match="AUDIT_APPEND_ONLY"):
                con.execute(text(sql))
        assert con.scalar(text("SELECT actor FROM vk_g_operation")) == "operation"
    engine.dispose()


def test_graph_audit_rollback_identity_and_failure_are_atomic(tmp_path, monkeypatch):
    url = "sqlite:///" + str(tmp_path / "atomic.db")
    monkeypatch.setenv("DATABASE_URL", url)
    command.upgrade(Config("alembic.ini"), "head")
    engine = create_engine(url)
    table = Base.metadata.tables["vk_g_identity"]
    with engine.connect() as con:
        con.execute(table.insert().values(**values("vk_g_identity", "rolled-back")))
        con.rollback()
        assert con.scalar(select(func.count()).select_from(table)) == 0
        assert con.scalar(text("SELECT count(*) FROM vk_change_event")) == 0
        assert con.scalar(text("SELECT count(*) FROM vk_change_outbox")) == 0
        con.commit()
    with engine.begin() as con:
        con.execute(table.insert().values(**values("vk_g_identity", "kept")))
        for field in ("owner_id", "id"):
            with pytest.raises(IntegrityError, match="AUDIT_IDENTITY_IMMUTABLE"):
                con.execute(table.update().values(**{field: "changed"}))
        con.exec_driver_sql(
            "CREATE TRIGGER reject_graph_audit BEFORE INSERT ON vk_change_outbox "
            "BEGIN SELECT RAISE(ABORT,'TEST_AUDIT_FAILURE'); END"
        )
        with pytest.raises(IntegrityError, match="TEST_AUDIT_FAILURE"):
            con.execute(table.update().values(status="LOST"))
        assert con.scalar(select(table.c.status)) == "kept"
        assert con.scalar(text("SELECT count(*) FROM vk_change_event")) == 1
        assert con.scalar(text("SELECT count(*) FROM vk_change_outbox")) == 1
    engine.dispose()


def test_oracle_extension_sql_and_compile_failure_gate():
    sql = statements("oracle")
    assert len(sql) == 6
    assert all("CREATE OR REPLACE TRIGGER" in item for item in sql)
    assert "lease_token" not in "\n".join(sql)
    assert "RETURNING CLOB" in sql[0]
    assert "DBMS_TRANSACTION.LOCAL_TRANSACTION_ID" in sql[0]
    assert "vk_audit_9" in sql[0] and "vk_audit_13" in sql[4]
    assert "BEFORE UPDATE OR DELETE ON vk_g_operation" in sql[-1]

    class Connection:
        dialect = type("Dialect", (), {"name": "oracle"})()

        def execute(self, statement):
            pass

        def exec_driver_sql(self, query):
            assert "USER_ERRORS" in query
            return type("Result", (), {"scalar_one": lambda self: 1})()

    with pytest.raises(RuntimeError, match="compilation failed"):
        install(Connection())
