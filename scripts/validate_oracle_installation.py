"""Opt-in isolated Oracle installation check using shipped migration/setup entrypoints."""

import argparse
import asyncio
import json
import os
import secrets
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from dotenv import dotenv_values
from sqlalchemy import DateTime, Integer, text
from sqlalchemy.exc import DatabaseError

from knowledge_app import audit_models, graph_auto_models, graph_ops_models  # noqa: F401
from knowledge_app.audit_schema_v11 import TABLES
from knowledge_app.database import database
from knowledge_app.models import Base
from knowledge_app.settings import ROOT, Settings


def guard_schema(actual: str, expected: str) -> None:
    if not expected or actual.upper() != expected.upper() or actual.upper() in {"ADMIN", "SYS", "SYSTEM"}:
        raise ValueError("Connect as the explicitly named isolated test schema, never ADMIN/SYS/SYSTEM")


def run_entrypoint(*args: str) -> None:
    subprocess.run([sys.executable, *args], cwd=ROOT, check=True)


def audit_probe(settings: Settings) -> None:
    engine = database(settings)
    owner = "validation:" + uuid4().hex
    try:
        with engine.connect() as con:
            guard_schema(str(con.scalar(text("SELECT USER FROM DUAL"))), settings.user_name)
            assert con.scalar(text("SELECT version_num FROM vk_alembic_version")) == "vk0011"
            assert con.scalar(text("SELECT count(*) FROM user_errors WHERE type='TRIGGER'")) == 0
            triggers = con.execute(
                text("SELECT trigger_name,status FROM user_triggers WHERE trigger_name LIKE 'VK_AUDIT_%'")
            ).all()
            required = {f"VK_AUDIT_{i}" for i in range(14)} | {
                "VK_AUDIT_APPEND_ONLY",
                "VK_AUDIT_OP_APPEND_ONLY",
            }
            assert required <= {r.trigger_name for r in triggers if r.status == "ENABLED"}
            for name in TABLES:
                table = Base.metadata.tables[name]
                identifier = uuid4().hex
                values = {}
                for column in table.columns:
                    if column.nullable:
                        continue
                    if isinstance(column.type, DateTime):
                        values[column.name] = datetime.now(UTC)
                    elif isinstance(column.type, Integer):
                        values[column.name] = 1
                    else:
                        values[column.name] = "{}" if column.name.endswith("_json") else "probe"
                values.update(id=identifier, owner_id=owner)
                for key in ("run_key", "binding_key", "candidate_key", "revision_id", "target_id"):
                    if key in table.c:
                        values[key] = uuid4().hex
                con.execute(table.insert().values(**values))
                if name == "vk_g_operation":
                    for statement in (
                        "UPDATE vk_g_operation SET actor='tampered' WHERE id=:id",
                        "DELETE FROM vk_g_operation WHERE id=:id",
                    ):
                        try:
                            con.execute(text(statement), {"id": identifier})
                        except DatabaseError as error:
                            if "ORA-20082" not in str(error):
                                raise
                        else:
                            raise ValueError("Operation history modification was not blocked")
                    continue
                con.execute(table.update().where(table.c.id == identifier).values(status="UPDATED"))
                con.execute(table.delete().where(table.c.id == identifier))
                rows = con.execute(
                    text(
                        "SELECT action,before_json,after_json FROM vk_change_event WHERE owner_id=:owner AND target_id=:id"
                    ),
                    {"owner": owner, "id": identifier},
                ).all()
                assert {r.action for r in rows} == {"INSERT", "UPDATE", "DELETE"}
                changed = next(r for r in rows if r.action == "UPDATE")
                assert json.loads(changed.before_json)["status"] == "probe"
                assert json.loads(changed.after_json)["status"] == "UPDATED"
            for table in ("vk_change_event", "vk_change_outbox"):
                assert (
                    con.scalar(text(f"SELECT count(*) FROM {table} WHERE owner_id=:owner"), {"owner": owner})
                    == 13
                )
            con.rollback()
            for table in ("vk_change_event", "vk_change_outbox"):
                assert (
                    con.scalar(text(f"SELECT count(*) FROM {table} WHERE owner_id=:owner"), {"owner": owner})
                    == 0
                )
            print("Oracle migration, 16 audit triggers, snapshots, append-only and rollback: PASS")
    finally:
        engine.dispose()


def model_graph_probe(settings: Settings) -> None:
    from fastapi.testclient import TestClient

    from knowledge_app.app import create_app
    from python_foundation.security import Actor
    from scripts.demo_graph_relations import run

    class Verifier:
        def verify(self, token: str) -> Actor:
            return Actor("isolated-installation-test", token, frozenset())

    app = create_app(settings, verifier=Verifier())
    try:
        with TestClient(app) as client:
            # Synthetic identities; this validates application ownership, not a production JWT provider.
            client.headers["Authorization"] = "Bearer " + secrets.token_hex(16)

            class API:
                async def request(self, method: str, path: str, **kwargs: object) -> object:
                    response = client.request(method, path, **kwargs)
                    if response.status_code >= 400:
                        raise ValueError(
                            f"Synthetic API check failed: {method} {path} ({response.status_code})"
                        )
                    if method == "POST" and path == "/api/v1/knowledge":
                        if not app.state.service.process_one():
                            raise ValueError("Ingestion worker did not process test source")
                    return response.json()

            asyncio.run(run(API()))
            result = client.post(
                "/api/v1/knowledge/search", json={"query": "Cafesto UX", "include_graph": True}
            ).json()
            assert result["items"] and result["graph"]["edges"]
            assert result["graph"]["candidate_backend"] == "oracle_property_graph"
            assert result["graph"]["storage"] == "oracle_rdf"
            client.headers["Authorization"] = "Bearer " + secrets.token_hex(16)
            assert client.post("/api/v1/knowledge/search", json={"query": "Cafesto UX"}).json()["items"] == []
            assert client.get("/api/v1/changes").json()["items"] == []
            print(
                "Configured embeddings, Oracle source READY/search, RDF/Property Graph, identity/review and owner isolation: PASS"
            )
    finally:
        app.state.engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-file", type=Path, required=True, help="Private test configuration; never commit it"
    )
    parser.add_argument("--expected-schema", required=True)
    parser.add_argument(
        "--apply", action="store_true", help="Apply migrations and run synthetic audit writes (rolled back)"
    )
    parser.add_argument("--graphs", action="store_true", help="Run shipped RDF/Property Graph initialization")
    parser.add_argument(
        "--models",
        action="store_true",
        help="Requires --graphs; persist fictional source/graph using configured embeddings",
    )
    args = parser.parse_args()
    if args.models and not args.graphs:
        parser.error("--models requires --graphs")
    if not args.apply:
        print(
            "Plan only: configure isolated schema, run Alembic upgrade head, then Oracle audit checks. Use --apply to execute."
        )
        return
    config = {k: v for k, v in dotenv_values(ROOT / ".env.example").items() if v is not None}
    config.update({k: v for k, v in dotenv_values(args.env_file).items() if v is not None})
    guard_schema(config.get("USER_NAME", ""), args.expected_schema)
    if not config.get("DATABASE_URL", "oracle").startswith("oracle"):
        raise ValueError("An Oracle test schema is required")
    config.update(
        WEB_PUBLIC_ORIGIN="",
        ENVIRONMENT="development",
        GRAPH_EXTRACTION_MODE="agent",
        GRAPH_AUTO_ENABLED="false",
    )
    os.environ.update(config)
    settings = Settings(_env_file=None)
    engine = database(settings)
    try:
        with engine.connect() as con:
            guard_schema(str(con.scalar(text("SELECT USER FROM DUAL"))), args.expected_schema)
    finally:
        engine.dispose()
    run_entrypoint("-m", "alembic", "-c", str(ROOT / "alembic.ini"), "upgrade", "head")
    audit_probe(settings)
    if args.graphs:
        run_entrypoint("-m", "scripts.prepare_knowledge_rdf")
        run_entrypoint("-m", "scripts.setup_property_graph", "--apply")
        os.environ.update(WORKFLOW_RDF_ENABLED="true", PROPERTY_GRAPH_ENABLED="true")
    if args.models:
        model_graph_probe(Settings(_env_file=None))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(
            f"Oracle validation FAILED ({type(error).__name__}); inspect the isolated schema and configuration.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
