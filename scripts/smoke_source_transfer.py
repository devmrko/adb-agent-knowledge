"""Isolated Oracle v3 transfer/restart/activation/rollback verification."""

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
from knowledge_app.contracts import CreateKnowledge
from knowledge_app.database import database
from knowledge_app.embedding import create_embedder
from knowledge_app.graph_contracts import AssertionInput, EntityInput, EvidenceInput
from knowledge_app.graph_service import GraphService
from knowledge_app.models import Event
from knowledge_app.service import KnowledgeService, owner_id
from knowledge_app.settings import Settings
from knowledge_app.source_transfer import SourceTransferService
from knowledge_app.v3_pilot import VersionedMemoryPilot
from python_foundation.database import sessions
from python_foundation.errors import BusinessError
from python_foundation.security import Actor


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--hf-home", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    os.environ["HF_HOME"] = str(args.hf_home.expanduser().resolve())
    os.environ["HF_HUB_OFFLINE"] = "1"
    values = {k.lower(): v for k, v in dotenv_values(args.env_file).items() if v is not None}
    if not values.get("user_name", "").startswith(("VKV_", "OAM_TEST_")):
        raise SystemExit("Requires isolated test account")
    settings = Settings(_env_file=None, **values).model_copy(
        update={
            "workflow_rdf_enabled": True,
            "property_graph_enabled": True,
            "agent_memory_store_id": "V3TRANSFER1103",
            "agent_memory_enabled": True,
            "embedding_revision": "55ec6e9358a56d56af759bc8372e970caf8c305f",
        }
    )
    config = Config("alembic.ini")
    config.attributes["settings"] = settings
    command.upgrade(config, "head")
    engine = database(settings)
    embedder = create_embedder(settings)
    sdk = SDKRepository(settings, embedder)
    source = KnowledgeService(sessions(engine), embedder, settings)
    graph = GraphService(sessions(engine), settings)
    pilot = VersionedMemoryPilot(source, sdk, graph)
    transfer = SourceTransferService(pilot)
    actor = Actor("v3-transfer-test", str(time.time_ns()), frozenset())
    scope = "project:v3-transfer-test"
    report = {"stage": "isolated Oracle transfer; production unchanged", "checks": []}

    def passed(name):
        report["checks"].append(name)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(name, flush=True)

    try:
        sdk.connect(initialize=True)
        body = "[합성 시험] Tasteby는 서버 A에 배포된다. 배포 실패 시 이전 배포로 복구한다."
        note = source.create(CreateKnowledge(title="v3 원문 전환 시험", text=body, scope=scope), actor)
        for _ in range(30):
            status = source.job(actor, note["job_id"])["status"]
            if status == "READY":
                break
            assert status != "FAILED"
            source.process_one()
        assert source.job(actor, note["job_id"])["status"] == "READY"
        kid, rid = note["knowledge_id"], note["revision_id"]
        transfer.enqueue(actor, kid, rid)
        # Simulate a post-SDK-write failure; durable retry must reuse the existing record.
        with patch.object(sdk, "verify_source_index", side_effect=RuntimeError("injected outage")):
            assert transfer.process_one()
        state = transfer.status(actor, rid)
        assert state["status"] == "FAILED"
        sdk.close()
        sdk = SDKRepository(settings, embedder)
        pilot = VersionedMemoryPilot(source, sdk, graph)
        transfer = SourceTransferService(pilot)
        transfer.change(actor, rid, state["generation"], "retry")
        assert transfer.process_one()
        assert transfer.status(actor, rid)["status"] == "VERIFIED"
        assert pilot.stage(actor, kid, rid)["reused"]
        passed("POST_WRITE_FAILURE_REOPEN_SDK_RETRY_REUSES_RECORD_AND_VERIFIES_CHUNKS")
        source.content_reader = transfer.content_owned
        graph.source_reader = transfer.content_owned
        state = transfer.status(actor, rid)
        transfer.change(actor, rid, state["generation"], "activate")
        with patch.object(source, "legacy_content", side_effect=AssertionError("legacy body read")):
            assert source.content(actor, kid, rid)["text"] == body
        passed("ACTIVE_SDK_SOURCE_READ_WITHOUT_LEGACY_CONTENT_ROUTE")
        a = graph.entity(
            actor, EntityInput(scope=scope, identity_key="tasteby", label="Tasteby", kind="project")
        )["id"]
        b = graph.entity(
            actor, EntityInput(scope=scope, identity_key="server-a", label="서버 A", kind="machine")
        )["id"]
        graph.assertion(
            actor,
            AssertionInput(
                scope=scope,
                subject_id=a,
                object_id=b,
                predicate="deployed_on",
                verified=True,
                evidence=[
                    EvidenceInput(knowledge_id=kid, revision_id=rid, quote="Tasteby는 서버 A에 배포된다.")
                ],
            ),
        )
        assert pilot.relations(actor, kid, rid)["edges"]
        passed("ROUTED_SDK_QUOTE_TO_RDF_PROPERTY_GRAPH")
        with patch.object(pilot, "read_owned", side_effect=RuntimeError("injected outage")):
            try:
                source.content(actor, kid, rid)
            except BusinessError:
                pass
            else:
                raise AssertionError("Unexpected silent fallback")
            state = transfer.status(actor, rid)
            transfer.change(actor, rid, state["generation"], "rollback")
            assert source.content(actor, kid, rid)["text"] == body
        passed("SDK_OUTAGE_FAILS_CLOSED_EXPLICIT_ROLLBACK_USES_RETAINED_SOURCE")
        with sessions(engine)() as session:
            events = session.scalars(
                select(Event.event_type).where(Event.owner_id == owner_id(actor), Event.revision_id == rid)
            ).all()
        assert "V3_ACTIVATE" in events and "V3_ROLLBACK" in events
        assert pilot.read(actor, kid, rid).text == body
        passed("TRANSITION_EVENTS_AND_BOTH_SOURCE_COPIES_PRESERVED")
    finally:
        sdk.close()
        engine.dispose()


if __name__ == "__main__":
    main()
