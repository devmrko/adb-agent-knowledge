"""Real child-process crashes and Oracle connection loss in an isolated test schema."""

import argparse
import json
import os
import select
import signal
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

from dotenv import dotenv_values
from sqlalchemy import func, text
from sqlalchemy import select as sql_select

from knowledge_app.agent_memory_repository import SDKRepository
from knowledge_app.contracts import CreateKnowledge, ReviseKnowledge, Search
from knowledge_app.database import database
from knowledge_app.embedding import create_embedder
from knowledge_app.graph_service import GraphService
from knowledge_app.models import Job
from knowledge_app.service import KnowledgeService
from knowledge_app.settings import ROOT, Settings
from knowledge_app.source_transfer import SourceTransferService
from knowledge_app.v3_pilot import VersionedMemoryPilot, record_key
from python_foundation.database import sessions
from python_foundation.security import Actor


def environment(path):
    values = {k: v for k, v in dotenv_values(ROOT / ".env.example").items() if v is not None}
    values.update({k: v for k, v in dotenv_values(path).items() if v is not None})
    if not values.get("USER_NAME", "").startswith(("VKV_", "OAM_TEST_")):
        raise ValueError("Only isolated test schemas are allowed")
    os.environ.update(values)
    os.environ["KNOWLEDGE_SOURCE_BACKEND"] = "v3"
    os.environ["HF_HUB_OFFLINE"] = "1"
    return Settings(_env_file=None)


def components(settings):
    engine = database(settings)
    service = KnowledgeService(sessions(engine), create_embedder(settings), settings)
    sdk = SDKRepository(
        settings.model_copy(update={"agent_memory_store_id": settings.knowledge_v3_store_id}),
        service.embedder,
    )
    transfer = SourceTransferService(
        VersionedMemoryPilot(service, sdk, GraphService(sessions(engine), settings))
    )
    transfer.attach()
    return engine, service, sdk


def child(settings, phase):
    engine, service, sdk = components(settings)
    original_stage, original_commit = service.ingestion_stage, service.ingestion_commit

    def stop():
        print("RECOVERY_POINT", flush=True)
        signal.pause()
        raise RuntimeError("Child must be killed, not resumed")

    def stage(*args):
        value = original_stage(*args)
        stop()
        return value

    def commit(session, *args):
        original_commit(session, *args)
        session.flush()
        if phase == "disconnect":
            session.connection().connection.driver_connection.close()
            session.execute(text("SELECT 1 FROM DUAL"))
        else:
            stop()

    if phase == "stage":
        service.ingestion_stage = stage
    else:
        service.ingestion_commit = commit
    try:
        assert service.process_one()
    finally:
        sdk.close()
        engine.dispose()


def run_child(env_file, phase):
    child_process = subprocess.Popen(
        [sys.executable, "-m", "scripts.smoke_v3_recovery", "--env-file", str(env_file), "--child", phase],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        if phase == "disconnect":
            assert child_process.wait(timeout=180) == 0
            return
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            if child_process.poll() is not None:
                raise RuntimeError("Worker exited before recovery checkpoint")
            ready, _, _ = select.select([child_process.stdout], [], [], 1)
            if ready and child_process.stdout.readline().strip() == "RECOVERY_POINT":
                child_process.kill()  # Only this test's own child; never an existing worker.
                assert child_process.wait(timeout=15) == -signal.SIGKILL
                return
        raise RuntimeError("Recovery checkpoint timed out")
    finally:
        if child_process.poll() is None:
            child_process.kill()
            child_process.wait()
        child_process.stdout.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--child", choices=["stage", "commit", "disconnect"])
    args = parser.parse_args()
    settings = environment(args.env_file)
    if args.child:
        child(settings, args.child)
        return
    if not args.output:
        parser.error("--output is required")
    engine, source, sdk = components(settings)
    actor = Actor("recovery-validation", uuid4().hex, frozenset())
    scope = "project:recovery-validation"
    report = {
        "date": "2026-11-03",
        "checks": [],
        "recovery": "manual RUNNING recovery after all test workers stopped",
        "connection_test": "real Oracle driver connection closed during transaction; not a network partition",
    }

    def passed(label):
        report["checks"].append(label)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
        print(label, flush=True)

    def worker():
        subprocess.run(
            [sys.executable, "-m", "knowledge_app.worker", "--once"],
            check=True,
            stdout=subprocess.DEVNULL,
            timeout=180,
        )

    try:
        with engine.connect() as con:
            assert con.scalar(text("SELECT USER FROM DUAL")) == settings.user_name.upper()
            assert (
                con.scalar(
                    sql_select(func.count()).select_from(Job).where(Job.status.in_(["QUEUED", "RUNNING"]))
                )
                == 0
            )
        old = source.create(
            CreateKnowledge(
                title="[합성 검증] 복구",
                text="Oracle 복구 시험의 현재 배포 위치는 서버 A입니다.",
                scope=scope,
            ),
            actor,
        )
        worker()
        assert source.job(actor, old["job_id"])["status"] == "READY"
        item_id, active_id = old["knowledge_id"], old["revision_id"]
        for index, phase in enumerate(["stage", "commit", "disconnect"], 1):
            new = source.revise(
                actor,
                item_id,
                ReviseKnowledge(
                    expected_revision_id=active_id,
                    text=f"Oracle 복구 시험의 새 배포 위치는 서버 {index}입니다.",
                    change_note="Synthetic recovery validation",
                ),
            )
            run_child(args.env_file.resolve(), phase)
            expected = "FAILED" if phase == "disconnect" else "RUNNING"
            assert source.job(actor, new["job_id"])["status"] == expected
            assert (
                source.search(actor, Search(query="Oracle 복구 배포", scopes=[scope]))["items"][0][
                    "revision_id"
                ]
                == active_id
            )
            assert source.content(actor, item_id, active_id)["text"]
            if phase == "disconnect":
                source.retry(actor, new["job_id"])
            else:
                subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "scripts.recover_knowledge_jobs",
                        "--workers-stopped",
                        "--job-id",
                        new["job_id"],
                    ],
                    check=True,
                    timeout=60,
                )
            worker()
            assert source.job(actor, new["job_id"])["status"] == "READY"
            assert (
                source.search(actor, Search(query="Oracle 복구 배포", scopes=[scope]))["items"][0][
                    "revision_id"
                ]
                == new["revision_id"]
            )
            current = source.content(actor, item_id, new["revision_id"])
            assert current["source_storage"]["record_id"]
            with engine.connect() as con:
                owner_id = con.scalar(sql_select(Job.owner_id).where(Job.id == new["job_id"]))
                key = record_key(owner_id, item_id, new["revision_id"])
                assert current["source_storage"]["record_id"] == key
                # Store name is validated by Settings; fixed test store is configured by the operator.
                assert (
                    con.scalar(
                        text(
                            f"SELECT count(*) FROM {settings.knowledge_v3_store_id}_MEMORY WHERE record_id=:key"
                        ),
                        {"key": key},
                    )
                    == 1
                )
            hist = source.history(actor, item_id)
            assert len(hist["revisions"]) == index + 1
            assert (
                len(
                    [
                        e
                        for e in hist["events"]
                        if e["event_type"] == "V3_INGEST" and e["revision_id"] == new["revision_id"]
                    ]
                )
                == 1
            )
            worker()
            assert source.history(actor, item_id)["events"] == hist["events"]
            active_id = new["revision_id"]
            passed(phase.upper() + "_OLD_VISIBLE_RECOVERED_ONCE_HISTORY_PRESERVED")
    finally:
        sdk.close()
        engine.dispose()


if __name__ == "__main__":
    main()
