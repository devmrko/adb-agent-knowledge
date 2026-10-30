"""Frozen vk0011 graph audit extension. Preserve applied migration semantics."""

import sqlalchemy as sa
from sqlalchemy.engine import Connection

TABLES: dict[str, tuple[str, tuple[str, ...]]] = {
    "vk_g_extract": (
        "id",
        (
            "id",
            "owner_id",
            "item_id",
            "revision_id",
            "run_key",
            "schema_version",
            "model",
            "status",
            "attempts",
            "retry_limit",
            "force_extract",
            "available_at",
            "created_at",
            "updated_at",
            "route_json",
            "error_code",
        ),
    ),
    "vk_g_proposal": (
        "id",
        (
            "id",
            "owner_id",
            "run_id",
            "item_id",
            "revision_id",
            "scope",
            "candidate_key",
            "payload_json",
            "status",
            "created_at",
            "reviewed_at",
            "reviewed_by",
            "review_note",
            "resolution_json",
            "assertion_id",
            "version_id",
        ),
    ),
    "vk_g_review": (
        "id",
        ("id", "owner_id", "item_id", "revision_id", "version", "status", "outcome", "note", "updated_at"),
    ),
    "vk_g_identity": (
        "id",
        (
            "id",
            "owner_id",
            "scope",
            "binding_key",
            "entity_id",
            "kind",
            "namespace",
            "value",
            "version",
            "status",
            "item_id",
            "revision_id",
            "quote",
            "note",
            "updated_at",
        ),
    ),
    "vk_g_operation": (
        "id",
        ("id", "owner_id", "target_id", "kind", "version", "actor", "snapshot_json", "created_at"),
    ),
}


def snapshot(table: str, prefix: str, oracle: bool) -> str:
    columns = TABLES[table][1]
    values = [f"'{name}' {'VALUE' if oracle else ','} {prefix}.{name}" for name in columns]
    return f"JSON_OBJECT({', '.join(values)}{' RETURNING CLOB' if oracle else ''})"


def statements(dialect: str) -> list[str]:
    result = []
    for n, (table, (pk, _)) in enumerate(TABLES.items(), start=9):
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
        result.append("""CREATE OR REPLACE TRIGGER vk_audit_op_append_only BEFORE UPDATE OR DELETE ON vk_g_operation
BEGIN RAISE_APPLICATION_ERROR(-20082,'AUDIT_APPEND_ONLY'); END;""")
    else:
        for action in ["UPDATE", "DELETE"]:
            result.append(
                f"CREATE TRIGGER IF NOT EXISTS vk_audit_op_no_{action.lower()} BEFORE {action} ON vk_g_operation BEGIN SELECT RAISE(ABORT,'AUDIT_APPEND_ONLY'); END"
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
