from datetime import timedelta
from types import SimpleNamespace

import pytest

from knowledge_app.models import Revision, SourceTransfer, now
from knowledge_app.service import owner_id
from knowledge_app.source_transfer import SourceTransferService
from knowledge_app.source_transfer_repository import TransferRepository
from python_foundation.database import SqlAlchemyUnitOfWork
from python_foundation.errors import BusinessError
from python_foundation.security import Actor
from tests.test_knowledge import knowledge as knowledge
from tests.test_v3_pilot import make


def setup(knowledge):
    pilot, store, note, actor = make(knowledge)
    pilot.sdk.settings = SimpleNamespace(agent_memory_store_id="TESTV3")
    pilot.sdk.verify_source_index = lambda *args: True
    transfer = SourceTransferService(pilot)
    pilot.source.content_reader = transfer.content_owned
    kid, rid = note["knowledge_id"], note["revision_id"]
    transfer.enqueue(actor, kid, rid)
    return transfer, store, actor, kid, rid


def transition(t, actor, rid, action):
    return t.change(actor, rid, t.status(actor, rid)["generation"], action)


def test_uncertain_write_persists_failed_and_restarts_without_duplicate(knowledge):
    t, store, actor, kid, rid = setup(knowledge)
    store.fail_after_add = True
    assert t.process_one()
    assert t.status(actor, rid)["status"] == "FAILED"
    assert len(store.rows) == 1
    store.fail_after_add = False
    restarted = SourceTransferService(t.pilot)
    transition(restarted, actor, rid, "retry")
    assert restarted.process_one()
    assert restarted.status(actor, rid)["status"] == "VERIFIED"
    assert len(store.rows) == 1
    assert not restarted.process_one()
    assert restarted.content(actor, kid, rid) is None


def test_active_sdk_read_does_not_need_legacy_body_and_fails_closed(knowledge):
    t, store, actor, kid, rid = setup(knowledge)
    assert t.process_one()
    transition(t, actor, rid, "activate")
    with SqlAlchemyUnitOfWork(t.factory) as uow:
        revision = uow.session.get(Revision, rid)
        original = revision.content_text
        revision.content_text = None
    assert t.pilot.source.content(actor, kid, rid)["text"] == original
    with pytest.raises(BusinessError):
        transition(t, actor, rid, "rollback")
    with SqlAlchemyUnitOfWork(t.factory) as uow:
        uow.session.get(Revision, rid).content_text = original
    rows = dict(store.rows)
    store.rows.clear()
    with pytest.raises(BusinessError):
        t.pilot.source.content(actor, kid, rid)
    # Explicit rollback succeeds even while SDK is unavailable, since legacy source is retained.
    transition(t, actor, rid, "rollback")
    assert t.pilot.source.content(actor, kid, rid)["text"] == original
    store.rows.update(rows)


def test_generation_owner_and_corrupt_index_guards(knowledge):
    t, store, actor, kid, rid = setup(knowledge)
    other = Actor("test", "bob", frozenset())
    with pytest.raises(BusinessError):
        t.enqueue(other, kid, rid)
    with pytest.raises(BusinessError):
        t.status(other, rid)
    t.pilot.sdk.verify_source_index = lambda *args: False
    t.process_one()
    assert t.status(actor, rid)["status"] == "FAILED"
    t.pilot.sdk.verify_source_index = lambda *args: True
    transition(t, actor, rid, "retry")
    t.process_one()
    before = t.status(actor, rid)["generation"]
    transition(t, actor, rid, "activate")
    with pytest.raises(BusinessError):
        t.change(actor, rid, before, "rollback")
    assert t.content(other, kid, rid) is None
    with pytest.raises(BusinessError):
        t.pilot.source.content(other, kid, rid)


def test_expired_lease_reclaimed_and_stale_worker_cannot_finish(knowledge):
    t, _, actor, _, rid = setup(knowledge)
    with SqlAlchemyUnitOfWork(t.factory) as uow:
        first = TransferRepository(uow.session).claim(t.store_id, t.profile)
    with SqlAlchemyUnitOfWork(t.factory) as uow:
        assert TransferRepository(uow.session).claim(t.store_id, t.profile) is None
        uow.session.get(SourceTransfer, (owner_id(actor), rid)).lease_until = now() - timedelta(seconds=1)
    with SqlAlchemyUnitOfWork(t.factory) as uow:
        repo = TransferRepository(uow.session)
        second = repo.claim(t.store_id, t.profile)
        assert second[2] != first[2]
        assert not repo.finish(*first, True)
        assert repo.finish(*second, False)
    assert t.status(actor, rid)["attempts"] == 2


def test_graph_quote_checks_use_active_sdk_source(knowledge):
    from knowledge_app.graph_contracts import AssertionInput, EntityInput, EvidenceInput
    from knowledge_app.graph_service import GraphService

    t, store, actor, kid, rid = setup(knowledge)
    t.process_one()
    transition(t, actor, rid, "activate")
    settings = t.pilot.source.settings.model_copy(update={"workflow_rdf_enabled": True})
    graph = GraphService(t.factory, settings)
    graph.source_reader = t.content_owned
    a = graph.entity(actor, EntityInput(identity_key="a", label="a", scope="project:test"))["id"]
    b = graph.entity(actor, EntityInput(identity_key="b", label="b", scope="project:test"))["id"]
    with SqlAlchemyUnitOfWork(t.factory) as uow:
        uow.session.get(Revision, rid).content_text = None
    request = AssertionInput(
        scope="project:test",
        subject_id=a,
        object_id=b,
        predicate="uses",
        verified=True,
        evidence=[EvidenceInput(knowledge_id=kid, revision_id=rid, quote="Oracle 배포")],
    )
    assert graph.assertion(actor, request)["version_id"]
    store.rows.clear()
    with pytest.raises(BusinessError):
        graph.assertion(actor, request)


def test_application_opt_in_uses_manifest_but_default_does_not(knowledge):
    client, service, _ = knowledge
    assert client.app.state.source_transfer is None
    assert service.content_reader is None


def test_opt_in_http_content_uses_sdk_with_owner_boundary(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from knowledge_app import app as application
    from knowledge_app.models import Base
    from knowledge_app.settings import Settings
    from tests.test_knowledge import TestEmbedder, TestVerifier
    from tests.test_v3_pilot import Store

    class FakeSDK:
        def __init__(self, settings, embedder):
            self.settings, self.store = settings, Store()

        def verify_source_index(self, *args):
            return True

        def close(self):
            pass

    monkeypatch.setattr(application, "SDKRepository", FakeSDK)
    settings = Settings(
        _env_file=None, database_url="sqlite:///" + str(tmp_path / "v3.db"), knowledge_source_backend="v3"
    )
    app = application.create_app(settings, embedder=TestEmbedder(), verifier=TestVerifier())
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer alice"
        note = client.post("/api/v1/knowledge", json={"title": "시험", "text": "Oracle 원문"}).json()
        source, t = app.state.service, app.state.source_transfer
        assert source.process_one()
        actor = Actor("test", "alice", frozenset())
        kid, rid = note["knowledge_id"], note["revision_id"]
        t.enqueue(actor, kid, rid)
        assert t.process_one()
        transition(t, actor, rid, "activate")
        with SqlAlchemyUnitOfWork(source.factory) as uow:
            uow.session.get(Revision, rid).content_text = None
        uri = f"/api/v1/knowledge/{kid}/revisions/{rid}/content"
        response = client.get(uri)
        assert response.status_code == 200, response.text
        assert response.json()["text"] == "Oracle 원문"
        client.headers["Authorization"] = "Bearer bob"
        assert client.get(uri).status_code == 404
