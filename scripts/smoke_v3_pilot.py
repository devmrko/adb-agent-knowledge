"""Three-document v3 SDK/RDF/Property Graph pilot in an isolated Oracle account."""

import argparse
import json
import os
import time
from pathlib import Path
from uuid import UUID

from dotenv import dotenv_values
from sqlalchemy import text

from knowledge_app.agent_memory_repository import SDKRepository
from knowledge_app.contracts import CreateKnowledge, ReviseKnowledge, Search
from knowledge_app.database import database
from knowledge_app.embedding import create_embedder
from knowledge_app.graph_contracts import AssertionInput, EntityInput, EvidenceInput
from knowledge_app.graph_service import GraphService
from knowledge_app.service import KnowledgeService
from knowledge_app.settings import Settings
from knowledge_app.v3_pilot import VersionedMemoryPilot
from python_foundation.database import sessions
from python_foundation.errors import BusinessError
from python_foundation.security import Actor


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env-file", required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--hf-home", type=Path)
    a = p.parse_args()
    if a.hf_home:
        os.environ["HF_HOME"] = str(a.hf_home.expanduser().resolve())
        os.environ["HF_HUB_OFFLINE"] = "1"
    values = {k.lower(): v for k, v in dotenv_values(a.env_file).items() if v is not None}
    if not values.get("user_name", "").startswith(("VKV_", "OAM_TEST_")):
        raise SystemExit("Requires isolated test account")
    settings = Settings(_env_file=None, **values).model_copy(
        update={
            "workflow_rdf_enabled": True,
            "property_graph_enabled": True,
            "agent_memory_store_id": "V3PILOT1103",
            "agent_memory_enabled": True,
            "embedding_revision": "55ec6e9358a56d56af759bc8372e970caf8c305f",
        }
    )
    engine = database(settings)
    with engine.connect() as c:
        for name in ["VK_KNOWLEDGE_GRAPH", "VK_FLOW_RDF#RDFT_VK_SHARED"]:
            assert c.execute(
                text("SELECT COUNT(*) FROM user_objects WHERE object_name=:name AND status='VALID'"),
                {"name": name},
            ).scalar_one(), "Initialize test RDF/Property Graph first"
    embedder = create_embedder(settings)
    sdk = SDKRepository(settings, embedder)
    source = KnowledgeService(sessions(engine), embedder, settings)
    graph = GraphService(sessions(engine), settings)
    pilot = VersionedMemoryPilot(source, sdk, graph)
    actor = Actor("v3-pilot", str(time.time_ns()), frozenset())
    scope = "project:v3-pilot"
    report = {"stage": "isolated pilot; production unchanged", "checks": []}

    def passed(name):
        report["checks"].append(name)
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(name, flush=True)

    def ready(saved):
        for _ in range(30):
            job = source.job(actor, saved["job_id"])
            if job["status"] == "READY":
                return
            assert job["status"] != "FAILED", job.get("error_code")
            source.process_one()
        raise AssertionError("Indexing did not finish")

    try:
        sdk.connect(initialize=True)
        notes = []
        for title, body in [
            (
                "배포 절차",
                "[합성 시험] Tasteby는 서버 A에 배포된다. 배포 전 테스트를 실행하고 실패하면 이전 배포로 복구한다.",
            ),
            (
                "화면 구성",
                "[합성 시험] Tasteby UX는 Tasteby의 일부다. 백오피스는 메뉴와 사용자 피드백을 관리한다.",
            ),
            (
                "개발 기반",
                "[합성 시험] Tasteby는 TypeScript Foundation에서 생성됐다. 공통 인증 기능을 재사용한다.",
            ),
        ]:
            note = source.create(CreateKnowledge(title=title, text=body, scope=scope), actor)
            ready(note)
            staged = pilot.stage(actor, note["knowledge_id"], note["revision_id"])
            assert staged["status"] == "READY"
            assert pilot.stage(actor, note["knowledge_id"], note["revision_id"])["reused"]
            assert pilot.read(actor, note["knowledge_id"], note["revision_id"]).text == body
            notes.append(note)
        passed("THREE_DOCUMENTS_EXACT_JSON_AND_IDEMPOTENT_STAGE")
        results = pilot.search(actor, "Tasteby 배포 실패 복구 절차", scope)
        assert notes[0]["knowledge_id"] in [r["knowledge_id"] for r in results["items"]]
        passed("REAL_KOREAN_EMBEDDER_SDK_SEARCH")
        try:
            pilot.read(
                Actor("v3-pilot", "other", frozenset()), notes[0]["knowledge_id"], notes[0]["revision_id"]
            )
        except BusinessError:
            passed("OTHER_OWNER_READ_DENIED")
        else:
            raise AssertionError("Owner isolation failed")
        entities = {}
        for key, label, kind in [
            ("app", "Tasteby", "project"),
            ("server-a", "서버 A", "machine"),
            ("server-b", "서버 B", "machine"),
        ]:
            entities[key] = graph.entity(
                actor, EntityInput(scope=scope, identity_key=key, label=label, kind=kind)
            )["id"]
        old = notes[0]
        claim = graph.assertion(
            actor,
            AssertionInput(
                scope=scope,
                subject_id=UUID(entities["app"]),
                predicate="deployed_on",
                object_id=UUID(entities["server-a"]),
                verified=True,
                evidence=[
                    EvidenceInput(
                        knowledge_id=UUID(old["knowledge_id"]),
                        revision_id=UUID(old["revision_id"]),
                        quote="Tasteby는 서버 A에 배포된다.",
                    )
                ],
            ),
        )
        linked = pilot.relations(actor, old["knowledge_id"], old["revision_id"])
        assert linked["edges"]
        relational = VersionedMemoryPilot(
            source,
            sdk,
            GraphService(sessions(engine), settings.model_copy(update={"property_graph_enabled": False})),
        )
        assert {e["version_id"] for e in linked["edges"]} == {
            e["version_id"]
            for e in relational.relations(actor, old["knowledge_id"], old["revision_id"])["edges"]
        }
        passed("SDK_REVISION_TO_RDF_AND_PROPERTY_GRAPH_MATCHES_RELATIONAL")
        changed = source.revise(
            actor,
            old["knowledge_id"],
            ReviseKnowledge(
                expected_revision_id=old["revision_id"],
                text="[합성 시험] Tasteby는 서버 B에 배포된다. 서버 A는 이전 배포 위치다.",
                change_note="v3 근거 현재성 검증",
            ),
        )
        ready(changed)
        pilot.stage(actor, changed["knowledge_id"], changed["revision_id"])
        assert "서버 A에 배포된다" in pilot.read(actor, old["knowledge_id"], old["revision_id"]).text
        assert not pilot.relations(actor, old["knowledge_id"], old["revision_id"])["edges"]
        assert all(
            row["revision_id"] != old["revision_id"]
            for row in pilot.search(actor, "Tasteby 배포", scope)["items"]
        )
        passed("OLD_VERSION_RETAINED_BUT_EXCLUDED_FROM_CURRENT_SEARCH_AND_GRAPH")
        graph.assertion(
            actor,
            AssertionInput(
                scope=scope,
                subject_id=UUID(entities["app"]),
                predicate="deployed_on",
                object_id=UUID(entities["server-b"]),
                verified=True,
                evidence=[
                    EvidenceInput(
                        knowledge_id=UUID(changed["knowledge_id"]),
                        revision_id=UUID(changed["revision_id"]),
                        quote="Tasteby는 서버 B에 배포된다.",
                    )
                ],
            ),
        )
        assert pilot.relations(actor, changed["knowledge_id"], changed["revision_id"])["edges"]
        assert graph.history(actor, claim["assertion_id"])
        passed("NEW_SOURCE_GRAPH_AND_OLD_ASSERTION_HISTORY")
        baseline = source.search(actor, Search(query="Tasteby 배포", scopes=[scope]))
        assert baseline["items"]
        assert (
            source.content(actor, old["knowledge_id"], old["revision_id"])["text"]
            == pilot.read(actor, old["knowledge_id"], old["revision_id"]).text
        )
        passed("V2_FALLBACK_AND_EXACT_HISTORICAL_SOURCE_PRESERVED")
    finally:
        sdk.close()
        engine.dispose()


if __name__ == "__main__":
    main()
