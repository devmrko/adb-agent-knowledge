import inspect
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Column, Integer, MetaData, String, Table, Text, delete, select, update

from knowledge_app import app as application
from knowledge_app.database import database
from knowledge_app.models import Base, Chunk, SourceTransfer, Vector
from tests import test_knowledge as original_knowledge
from tests import test_shared_graph as original_graph
from tests.test_knowledge import TestEmbedder, TestVerifier
from tests.test_v3_pilot import Store


class FakeSDK:
    instances = []

    def __init__(self, settings, embedder):
        self.settings, self.embedder = settings, embedder
        self.engine = database(settings)
        metadata = MetaData()
        self.chunks = Table(
            settings.agent_memory_store_id + "_RECORD_CHUNKS",
            metadata,
            Column("source_id", String(64)),
            Column("source_record_type", String(32)),
            Column("user_id", String(64)),
            Column("chunk_seq", Integer()),
            Column("chunk_text", Text()),
            Column("embedding", Vector()),
        )
        metadata.create_all(self.engine)
        self.store = Store()
        self.fail = False
        self.original_add = self.store.add
        self.store.add = self.add
        self.instances.append(self)

    def add(self, **kwargs):
        if self.fail:
            raise RuntimeError("private provider error")
        self.original_add(**kwargs)
        chunks = kwargs["index_texts"][0]
        vectors = self.embedder.encode(chunks)
        with self.engine.begin() as c:
            c.execute(
                self.chunks.insert(),
                [
                    dict(
                        source_id=kwargs["record_ids"],
                        source_record_type="memory",
                        user_id=kwargs["user_ids"],
                        chunk_seq=n + 1,
                        chunk_text=text,
                        embedding=vector,
                    )
                    for n, (text, vector) in enumerate(zip(chunks, vectors, strict=True))
                ],
            )

    def verify_source_index(self, key, owner, chunks):
        with self.engine.connect() as c:
            texts = c.scalars(
                select(self.chunks.c.chunk_text)
                .where(self.chunks.c.source_id == key, self.chunks.c.user_id == owner)
                .order_by(self.chunks.c.chunk_seq)
            ).all()
        return texts == chunks

    def close(self):
        self.engine.dispose()


@pytest.fixture
def v3(tmp_path, monkeypatch):
    from knowledge_app.settings import Settings

    FakeSDK.instances = []
    monkeypatch.setattr(application, "SDKRepository", FakeSDK)
    settings = Settings(
        _env_file=None,
        database_url="sqlite:///" + str(tmp_path / "primary.db"),
        knowledge_source_backend="v3",
        workflow_rdf_enabled=True,
    )
    app = application.create_app(settings, embedder=TestEmbedder(), verifier=TestVerifier())
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as c:
        c.headers["Authorization"] = "Bearer alice"
        yield SimpleNamespace(
            client=c,
            source=app.state.service,
            transfer=app.state.source_transfer,
            sdk=FakeSDK.instances[-1],
            engine=app.state.engine,
        )


def save(v3, text="Oracle 배포 ORA-12345", **extra):
    response = v3.client.post("/api/v1/knowledge", json={"title": "시험", "text": text, **extra})
    assert response.status_code == 202, response.text
    note = response.json()
    assert v3.source.process_one()
    assert v3.client.get("/api/v1/jobs/" + note["job_id"]).json()["status"] == "READY"
    return note


def search(v3, **extra):
    response = v3.client.post("/api/v1/knowledge/search", json={"query": "Oracle", **extra})
    assert response.status_code == 200, response.text
    return response.json()["items"]


def content(v3, note):
    return v3.client.get(f"/api/v1/knowledge/{note['knowledge_id']}/revisions/{note['revision_id']}/content")


def test_new_write_uses_sdk_vectors_and_keywords_not_shadow(v3):
    note = save(v3, scope="project:a", category="runbook", memory_kind="PROCEDURE")
    # Corrupt only the rollback shadow: normal retrieval must still use SDK text/vectors.
    with v3.engine.begin() as c:
        c.execute(update(Chunk).values(text="wrong shadow", embedding=[0.0, 1.0] + [0.0] * 1022))
    rows = search(v3, scopes=["project:a"])
    assert rows[0]["revision_id"] == note["revision_id"]
    assert rows[0]["similarity"] > 0.99
    assert rows[0]["matches"][0]["text"] == "Oracle 배포 ORA-12345"
    assert search(v3, query="ORA-12345", min_similarity=1.0)[0]["keyword_coverage"] == 1.0
    assert not search(v3, scopes=["project:b"])
    assert not search(v3, category="other")
    assert not search(v3, memory_kinds=["PREFERENCE"])
    assert search(v3, knowledge_type="NOTE")
    v3.client.headers["Authorization"] = "Bearer bob"
    assert not search(v3)
    assert content(v3, note).status_code == 404


def test_revision_failure_preserves_old_current_retry_history_retire_restore(v3):
    old = save(v3)
    response = v3.client.post(
        "/api/v1/knowledge/" + old["knowledge_id"] + "/revisions",
        json={"expected_revision_id": old["revision_id"], "text": "Oracle 새 배포", "change_note": "수정"},
    )
    assert response.status_code == 202, response.text
    new = response.json()
    v3.sdk.fail = True
    assert v3.source.process_one()
    assert v3.client.get("/api/v1/jobs/" + new["job_id"]).json()["status"] == "FAILED"
    assert search(v3)[0]["revision_id"] == old["revision_id"]
    assert "private provider" not in str(v3.client.get("/api/v1/jobs/" + new["job_id"]).json())
    v3.sdk.fail = False
    assert v3.client.post("/api/v1/jobs/" + new["job_id"] + "/retry").status_code == 202
    assert v3.source.process_one()
    assert search(v3)[0]["revision_id"] == new["revision_id"]
    assert content(v3, old).json()["text"] == "Oracle 배포 ORA-12345"
    assert content(v3, new).json()["text"] == "Oracle 새 배포"
    history = v3.client.get("/api/v1/knowledge/" + old["knowledge_id"] + "/history").json()
    assert len(history["revisions"]) == 2
    assert len([e for e in history["events"] if e["event_type"] == "V3_INGEST"]) == 2
    assert (
        v3.client.post(
            "/api/v1/knowledge/" + old["knowledge_id"] + "/retire", json={"reason": "시험"}
        ).status_code
        == 200
    )
    assert not search(v3)
    assert search(v3, include_retired=True)
    assert (
        v3.client.post(
            "/api/v1/knowledge/" + old["knowledge_id"] + "/restore", json={"reason": "시험"}
        ).status_code
        == 200
    )
    assert search(v3)


def test_missing_sdk_chunk_fails_instead_of_returning_partial_results(v3):
    note = save(v3)
    with v3.engine.begin() as c:
        c.execute(delete(v3.sdk.chunks))
    response = v3.client.post("/api/v1/knowledge/search", json={"query": "Oracle"})
    assert response.status_code == 503, response.text
    assert "V3_SEARCH_INCOMPLETE" in response.text
    assert content(v3, note).status_code == 200


def test_ingestion_manifest_and_current_version_commit_together(v3, monkeypatch):
    original = v3.source.ingestion_commit

    def fail_commit(*args):
        original(*args)
        raise RuntimeError("injected final transaction failure")

    monkeypatch.setattr(v3.source, "ingestion_commit", fail_commit)
    note = v3.client.post("/api/v1/knowledge", json={"title": "시험", "text": "Oracle 원문"}).json()
    assert v3.source.process_one()
    with v3.engine.connect() as c:
        assert (
            c.scalar(
                select(SourceTransfer.revision_id).where(SourceTransfer.revision_id == note["revision_id"])
            )
            is None
        )
    assert not search(v3)
    assert len(v3.sdk.store.rows) == 1  # SDK orphan is invisible without committed publication.
    monkeypatch.setattr(v3.source, "ingestion_commit", original)
    assert v3.client.post("/api/v1/jobs/" + note["job_id"] + "/retry").status_code == 202
    assert v3.source.process_one()
    assert len(v3.sdk.store.rows) == 1
    assert search(v3)


# Re-run the existing behavior contracts against the primary SDK backend.


SCENARIOS = [
    value
    for module in [original_knowledge, original_graph]
    for name, value in vars(module).items()
    if name.startswith("test_")
    and callable(value)
    and list(inspect.signature(value).parameters) in [["knowledge"], ["knowledge_fixture"]]
]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda fn: fn.__name__)
def test_existing_contracts_on_v3(v3, scenario):
    scenario((v3.client, v3.source, v3.source.embedder))
