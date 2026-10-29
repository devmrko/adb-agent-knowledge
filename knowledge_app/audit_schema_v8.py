"""Frozen vk0008 schema and row triggers. Keep migration semantics stable."""

from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.oracle import TIMESTAMP
from sqlalchemy.engine import Connection

TABLES: dict[str, tuple[str, tuple[str, ...]]] = {
    "vk_item": (
        "id",
        (
            "id",
            "owner_id",
            "title",
            "knowledge_type",
            "category",
            "tags_json",
            "memory_kind",
            "scope",
            "active_revision_id",
            "lifecycle_status",
            "superseded_by_id",
            "retired_at",
        ),
    ),
    "vk_revision": (
        "id",
        (
            "id",
            "owner_id",
            "item_id",
            "revision_no",
            "change_note",
            "edit_origin",
            "origin_machine_id",
            "origin_machine_label",
            "sources_json",
            "content_text",
            "summary_text",
            "summary_kind",
            "source_type",
            "source_url",
            "filename",
            "mime_type",
        ),
    ),
    "vk_index": ("id", ("id", "owner_id", "scope", "key", "title", "summary", "body", "version")),
    "vk_index_entry": ("id", ("id", "owner_id", "index_id", "item_id", "section", "position", "note")),
    "vk_g_entity": ("id", ("id", "owner_id", "scope", "identity_key", "label", "kind", "aliases_json")),
    "vk_g_claim": ("id", ("id", "owner_id", "scope", "current_version_id", "signature")),
    "vk_g_version": (
        "id",
        (
            "id",
            "owner_id",
            "claim_id",
            "scope",
            "subject_id",
            "object_id",
            "predicate",
            "temporal_kind",
            "valid_from",
            "valid_to",
            "recorded_from",
            "recorded_to",
            "status",
            "payload_json",
        ),
    ),
    "vk_g_evidence": ("id", ("id", "owner_id", "version_id", "knowledge_id", "revision_id", "quote")),
    "vk_workflow": ("revision_id", ("revision_id", "owner_id", "payload_json", "payload_hash")),
}


def tables(metadata: sa.MetaData) -> dict[str, sa.Table]:
    timestamp = sa.DateTime(timezone=True).with_variant(TIMESTAMP(timezone=True), "oracle")

    def col(name: str, kind: Any, nullable: bool = False, **kwargs: Any) -> sa.Column[Any]:
        return sa.Column(name, kind, nullable=nullable, **kwargs)

    context = sa.Table(
        "vk_change_context",
        metadata,
        col("id", sa.String(36), primary_key=True),
        col("owner_id", sa.String(64)),
        col("transaction_id", sa.String(100), True, index=True),
        col("operation", sa.String(80)),
        col("request_id", sa.String(36)),
        col("actor_subject", sa.String(500), True),
        col("actor_issuer", sa.String(500), True),
        col("machine_id", sa.String(100), True),
        col("edit_origin", sa.String(16), True),
        col("reason", sa.String(500), True),
        col("source", sa.String(16)),
        col("created_at", timestamp),
    )
    change = sa.Table(
        "vk_change_event",
        metadata,
        col("id", sa.String(36), primary_key=True),
        col("owner_id", sa.String(64), index=True),
        col("context_id", sa.String(36), True),
        col("table_name", sa.String(40)),
        col("target_id", sa.String(36), index=True),
        col("action", sa.String(10)),
        col("before_json", sa.Text(), True),
        col("after_json", sa.Text(), True),
        col("db_user", sa.String(128), True),
        col("created_at", timestamp, index=True),
    )
    outbox = sa.Table(
        "vk_change_outbox",
        metadata,
        col("event_id", sa.String(36), primary_key=True),
        col("owner_id", sa.String(64), index=True),
        col("status", sa.String(16), index=True),
        col("attempts", sa.Integer()),
        col("retry_limit", sa.Integer()),
        col("available_at", timestamp),
        col("processed_at", timestamp, True),
        col("error_code", sa.String(80), True),
        sa.ForeignKeyConstraint(["event_id"], ["vk_change_event.id"]),
    )
    review = sa.Table(
        "vk_change_review",
        metadata,
        col("id", sa.String(36), primary_key=True),
        col("owner_id", sa.String(64), index=True),
        col("event_id", sa.String(36)),
        col("target_type", sa.String(40)),
        col("target_id", sa.String(36)),
        col("reason", sa.String(80)),
        col("status", sa.String(16), index=True),
        col("created_at", timestamp),
        col("resolved_at", timestamp, True),
        col("resolution_note", sa.String(1000), True),
        col("resolved_by", sa.String(500), True),
        sa.UniqueConstraint("event_id", "target_type", "target_id", "reason", name="vk_change_review_uq"),
    )
    return {t.name: t for t in [context, change, outbox, review]}


def snapshot(table: str, prefix: str, oracle: bool) -> str:
    columns = TABLES[table][1]
    values = [f"'{name}' {'VALUE' if oracle else ','} {prefix}.{name}" for name in columns]
    if table == "vk_revision":
        size = f"DBMS_LOB.GETLENGTH({prefix}.original_data)" if oracle else f"length({prefix}.original_data)"
        values.append(f"'original_bytes' {'VALUE' if oracle else ','} {size}")
    return f"JSON_OBJECT({', '.join(values)}{' RETURNING CLOB' if oracle else ''})"


def statements(dialect: str) -> list[str]:
    result = []
    for n, (table, (pk, _)) in enumerate(TABLES.items()):
        if dialect == "oracle":
            result.append(f"""CREATE OR REPLACE TRIGGER vk_audit_{n}
AFTER INSERT OR UPDATE OR DELETE ON {table} FOR EACH ROW
DECLARE v_id VARCHAR2(36); v_owner VARCHAR2(64); v_target VARCHAR2(36); v_context VARCHAR2(36);
v_before CLOB; v_after CLOB; v_action VARCHAR2(10);
BEGIN
 IF UPDATING AND (:OLD.owner_id <> :NEW.owner_id OR :OLD.{pk} <> :NEW.{pk}) THEN
  RAISE_APPLICATION_ERROR(-20081,'AUDIT_IDENTITY_IMMUTABLE'); END IF;
 v_id := LOWER(RAWTOHEX(SYS_GUID()));
 IF DELETING THEN v_owner:=:OLD.owner_id; v_target:=:OLD.{pk}; v_action:='DELETE';
 ELSE v_owner:=:NEW.owner_id; v_target:=:NEW.{pk};
  IF INSERTING THEN v_action:='INSERT'; ELSE v_action:='UPDATE'; END IF;
 END IF;
 IF NOT INSERTING THEN SELECT {snapshot(table, ":OLD", True)} INTO v_before FROM dual; END IF;
 IF NOT DELETING THEN SELECT {snapshot(table, ":NEW", True)} INTO v_after FROM dual; END IF;
 BEGIN SELECT id INTO v_context FROM vk_change_context
  WHERE transaction_id=DBMS_TRANSACTION.LOCAL_TRANSACTION_ID AND owner_id=v_owner;
 EXCEPTION WHEN NO_DATA_FOUND THEN v_context:=NULL; END;
 INSERT INTO vk_change_event(id,owner_id,context_id,table_name,target_id,action,before_json,after_json,db_user,created_at)
 VALUES(v_id,v_owner,v_context,'{table}',v_target,v_action,v_before,v_after,SYS_CONTEXT('USERENV','SESSION_USER'),SYSTIMESTAMP);
 INSERT INTO vk_change_outbox(event_id,owner_id,status,attempts,retry_limit,available_at)
 VALUES(v_id,v_owner,'PENDING',0,5,SYSTIMESTAMP);
END;""")
        else:
            result.append(
                f"CREATE TRIGGER IF NOT EXISTS vk_audit_identity_{n} BEFORE UPDATE ON {table} WHEN OLD.owner_id <> NEW.owner_id OR OLD.{pk} <> NEW.{pk} BEGIN SELECT RAISE(ABORT,'AUDIT_IDENTITY_IMMUTABLE'); END"
            )
            for action in ["INSERT", "UPDATE", "DELETE"]:
                row = "OLD" if action == "DELETE" else "NEW"
                before = "NULL" if action == "INSERT" else snapshot(table, "OLD", False)
                after = "NULL" if action == "DELETE" else snapshot(table, "NEW", False)
                result.append(f"""CREATE TRIGGER IF NOT EXISTS vk_audit_{n}_{action.lower()} AFTER {action} ON {table}
BEGIN
 INSERT INTO vk_change_event(id,owner_id,context_id,table_name,target_id,action,before_json,after_json,db_user,created_at)
 VALUES(lower(hex(randomblob(16))),{row}.owner_id,
 (SELECT id FROM vk_change_context WHERE transaction_id='SQLITE_ACTIVE' AND owner_id={row}.owner_id),
 '{table}',{row}.{pk},'{action}',{before},{after},'sqlite',strftime('%Y-%m-%d %H:%M:%f','now'));
 INSERT INTO vk_change_outbox(event_id,owner_id,status,attempts,retry_limit,available_at)
 SELECT id,owner_id,'PENDING',0,5,created_at FROM vk_change_event WHERE rowid=last_insert_rowid();
END""")
    if dialect == "oracle":
        result.append("""CREATE OR REPLACE TRIGGER vk_audit_append_only BEFORE UPDATE OR DELETE ON vk_change_event
BEGIN RAISE_APPLICATION_ERROR(-20082,'AUDIT_APPEND_ONLY'); END;""")
    else:
        for action in ["UPDATE", "DELETE"]:
            result.append(
                f"CREATE TRIGGER IF NOT EXISTS vk_audit_no_{action.lower()} BEFORE {action} ON vk_change_event BEGIN SELECT RAISE(ABORT,'AUDIT_APPEND_ONLY'); END"
            )
    return result


def install(connection: Connection) -> None:
    dialect = connection.dialect.name
    if dialect not in {"sqlite", "oracle"}:
        raise ValueError("Audit triggers support SQLite and Oracle")
    for sql in statements(dialect):
        connection.execute(sa.DDL(sql.replace("%", "%%")))  # type: ignore[no-untyped-call]
    if dialect == "oracle" and hasattr(connection, "exec_driver_sql"):
        invalid = connection.exec_driver_sql(
            "SELECT COUNT(*) FROM USER_ERRORS WHERE TYPE='TRIGGER' AND NAME LIKE 'VK_AUDIT_%'"
        ).scalar_one()
        if invalid:
            raise RuntimeError("Audit trigger compilation failed; inspect USER_ERRORS")
