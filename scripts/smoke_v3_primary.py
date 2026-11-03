"""Verify the primary SDK write/search lifecycle in an isolated Oracle schema."""

import argparse
import json
import os
import time
from pathlib import Path
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from dotenv import dotenv_values
from sqlalchemy import select

from knowledge_app.agent_memory_repository import SDKRepository
from knowledge_app.contracts import (
    CreateKnowledge,
    RestoreKnowledge,
    RetireKnowledge,
    ReviseKnowledge,
    Search,
)
from knowledge_app.database import database
from knowledge_app.embedding import create_embedder
from knowledge_app.graph_contracts import AssertionInput, EntityInput, EvidenceInput
from knowledge_app.graph_service import GraphService
from knowledge_app.models import SourceTransfer
from knowledge_app.service import KnowledgeService
from knowledge_app.settings import Settings
from knowledge_app.source_transfer import SourceTransferService
from knowledge_app.v3_pilot import VersionedMemoryPilot
from python_foundation.database import sessions
from python_foundation.security import Actor


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env-file", required=True)
    p.add_argument("--hf-home", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    os.environ["HF_HOME"] = str(args.hf_home.resolve())
    os.environ["HF_HUB_OFFLINE"] = "1"
    values = {k.lower(): v for k, v in dotenv_values(args.env_file).items() if v is not None}
    if not values.get("user_name", "").startswith(("VKV_", "OAM_TEST_")):
        raise SystemExit("Requires isolated test schema")
    s = Settings(_env_file=None, **values).model_copy(
        update={
            "knowledge_source_backend": "v3",
            "knowledge_v3_store_id": "V3PRIMARY1103",
            "workflow_rdf_enabled": True,
            "property_graph_enabled": True,
            "embedding_revision": "55ec6e9358a56d56af759bc8372e970caf8c305f",
        }
    )
    cfg = Config("alembic.ini")
    cfg.attributes["settings"] = s
    command.upgrade(cfg, "head")
    engine = database(s)
    embedder = create_embedder(s)
    source = KnowledgeService(sessions(engine), embedder, s)
    graph = GraphService(sessions(engine), s)
    sdk = SDKRepository(s.model_copy(update={"agent_memory_store_id": s.knowledge_v3_store_id}), embedder)
    pilot = VersionedMemoryPilot(source, sdk, graph)
    t = SourceTransferService(pilot)
    t.attach()
    graph.source_reader = t.content_owned
    actor = Actor("v3-primary-test", str(time.time_ns()), frozenset())
    scope = "project:v3-primary-test"
    report = {"checks": [], "stage": "isolated primary SDK lifecycle"}

    def passed(label):
        report["checks"].append(label)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(label, flush=True)

    def process(note, expected="READY"):
        for _ in range(30):
            state = source.job(actor, note["job_id"])["status"]
            if state in {"READY", "FAILED"}:
                assert state == expected, state
                return
            source.process_one()
        raise AssertionError("Job did not finish")

    def query():
        return source.search(actor, Search(query="Oracle 배포", scopes=[scope]))["items"]

    try:
        sdk.connect(initialize=True)
        old = source.create(
            CreateKnowledge(
                title="배포",
                text="[합성 시험] Tasteby는 서버 A에 배포된다. Oracle 오류 ORA-12345를 확인한다.",
                scope=scope,
            ),
            actor,
        )
        process(old)
        assert t.status(actor, old["revision_id"])["status"] == "ACTIVE"
        assert query()[0]["revision_id"] == old["revision_id"]
        exact = source.search(actor, Search(query="ORA-12345", scopes=[scope], min_similarity=1.0))["items"]
        assert exact and exact[0]["keyword_coverage"] == 1.0
        assert not source.search(
            Actor("v3-primary-test", "other", frozenset()), Search(query="Oracle", scopes=[scope])
        )["items"]
        passed("AUTOMATIC_SDK_WRITE_PUBLICATION_VECTOR_KEYWORD_SEARCH_OWNER_FILTER")
        legacy = KnowledgeService(
            sessions(engine), embedder, s.model_copy(update={"knowledge_source_backend": "legacy"})
        )
        assert [
            x["knowledge_id"]
            for x in legacy.search(actor, Search(query="Oracle 배포", scopes=[scope]))["items"]
        ] == [x["knowledge_id"] for x in query()]
        passed("LEGACY_AND_SDK_RANKED_TARGET_MATCH")
        a = graph.entity(
            actor, EntityInput(scope=scope, identity_key="app", label="Tasteby", kind="project")
        )["id"]
        b = graph.entity(
            actor, EntityInput(scope=scope, identity_key="server", label="서버 A", kind="machine")
        )["id"]
        assertion = graph.assertion(
            actor,
            AssertionInput(
                scope=scope,
                subject_id=a,
                object_id=b,
                predicate="deployed_on",
                verified=True,
                evidence=[
                    EvidenceInput(
                        knowledge_id=old["knowledge_id"],
                        revision_id=old["revision_id"],
                        quote="Tasteby는 서버 A에 배포된다.",
                    )
                ],
            ),
        )
        assert pilot.relations(actor, old["knowledge_id"], old["revision_id"])["edges"]
        new = source.revise(
            actor,
            old["knowledge_id"],
            ReviseKnowledge(
                expected_revision_id=old["revision_id"],
                text="[합성 시험] Tasteby는 서버 B에 배포된다. Oracle 배포 위치를 변경했다.",
                change_note="v3 수정 시험",
            ),
        )
        with patch.object(sdk, "verify_source_index", side_effect=RuntimeError("injected post-write outage")):
            process(new, "FAILED")
        assert query()[0]["revision_id"] == old["revision_id"]
        assert pilot.relations(actor, old["knowledge_id"], old["revision_id"])["edges"]
        passed("POST_SDK_WRITE_FAILURE_KEEPS_OLD_SEARCH_AND_GRAPH_CURRENT")
        source.retry(actor, new["job_id"])
        process(new)
        assert query()[0]["revision_id"] == new["revision_id"]
        assert pilot.stage(actor, new["knowledge_id"], new["revision_id"])["reused"]
        assert "서버 A" in source.content(actor, old["knowledge_id"], old["revision_id"])["text"]
        assert not pilot.relations(actor, old["knowledge_id"], old["revision_id"])["edges"]
        assert graph.history(actor, assertion["assertion_id"])
        hist = source.history(actor, old["knowledge_id"])
        assert len(hist["revisions"]) == 2
        assert len([e for e in hist["events"] if e["event_type"] == "V3_INGEST"]) == 2
        passed("RETRY_REUSES_SDK_RECORD_PRESERVES_SOURCE_GRAPH_AND_CHANGE_HISTORY")
        source.retire(actor, old["knowledge_id"], RetireKnowledge(reason="합성 시험"))
        assert not query()
        assert source.search(actor, Search(query="Oracle", scopes=[scope], include_retired=True))["items"]
        source.restore(actor, old["knowledge_id"], RestoreKnowledge(reason="합성 시험"))
        assert query()
        assert source.original(actor, old["knowledge_id"], old["revision_id"])[0]
        with sessions(engine)() as db:
            assert db.scalar(
                select(SourceTransfer.sdk_record_id).where(SourceTransfer.revision_id == new["revision_id"])
            )
        passed("RETIRE_RESTORE_ORIGINAL_ATTACHMENT_STABLE_ID")
    finally:
        sdk.close()
        engine.dispose()


if __name__ == "__main__":
    main()
