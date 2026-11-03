from types import SimpleNamespace

import pytest

from knowledge_app.contracts import ReviseKnowledge
from knowledge_app.v3_pilot import VersionedMemoryPilot
from python_foundation.errors import BusinessError
from python_foundation.security import Actor
from tests.test_knowledge import knowledge as knowledge


class Store:
    def __init__(self):
        self.rows = {}
        self.fail_after_add = False

    def get(self, kind, key):
        return self.rows.get(key)

    def add(self, *, contents, record_ids, user_ids, metadata, **kwargs):
        self.rows[record_ids] = SimpleNamespace(
            id=record_ids, user_id=user_ids, content=contents[0], metadata=dict(metadata)
        )
        if self.fail_after_add:
            raise RuntimeError("private provider token must not escape")

    def search(self, query, **kwargs):
        return [
            (r, 0.8)
            for r in self.rows.values()
            if r.user_id == kwargs["user_id"]
            and all(r.metadata.get(k) == v for k, v in kwargs["metadata_filter"].items())
        ]


def make(knowledge):
    client, service, _ = knowledge
    saved = client.post(
        "/api/v1/knowledge", json={"title": "시험", "text": "Oracle 배포", "scope": "project:test"}
    ).json()
    assert service.process_one()
    store = Store()
    pilot = VersionedMemoryPilot(service, SimpleNamespace(store=store), None)
    return pilot, store, saved, Actor("test", "alice", frozenset())


def test_retry_after_uncertain_sdk_write_reuses_revision(knowledge):
    pilot, store, note, actor = make(knowledge)
    store.fail_after_add = True
    with pytest.raises(BusinessError) as e:
        pilot.stage(actor, note["knowledge_id"], note["revision_id"])
    assert "private provider" not in str(e.value)
    store.fail_after_add = False
    assert pilot.stage(actor, note["knowledge_id"], note["revision_id"])["reused"]
    assert len(store.rows) == 1


def test_revision_isolation_and_current_search(knowledge):
    pilot, store, note, actor = make(knowledge)
    pilot.stage(actor, note["knowledge_id"], note["revision_id"])
    other = Actor("test", "bob", frozenset())
    with pytest.raises(BusinessError):
        pilot.read(other, note["knowledge_id"], note["revision_id"])
    with pytest.raises(BusinessError):
        pilot.stage(other, note["knowledge_id"], note["revision_id"])
    changed = pilot.source.revise(
        actor,
        note["knowledge_id"],
        ReviseKnowledge(expected_revision_id=note["revision_id"], text="Oracle 새 배포", change_note="test"),
    )
    assert pilot.source.process_one()
    assert pilot.search(actor, "배포", "project:test")["items"] == []
    pilot.stage(actor, changed["knowledge_id"], changed["revision_id"])
    rows = pilot.search(actor, "배포", "project:test")["items"]
    assert [r["revision_id"] for r in rows] == [changed["revision_id"]]
    assert pilot.read(actor, note["knowledge_id"], note["revision_id"]).text == "Oracle 배포"
    assert len(store.rows) == 2


def test_tampered_record_rejected_and_not_overwritten(knowledge):
    pilot, store, note, actor = make(knowledge)
    saved = pilot.stage(actor, note["knowledge_id"], note["revision_id"])
    row = store.rows[saved["record_id"]]
    row.content = row.content.replace("Oracle 배포", "다른 원문")
    with pytest.raises(BusinessError):
        pilot.read(actor, note["knowledge_id"], note["revision_id"])
    with pytest.raises(BusinessError):
        pilot.stage(actor, note["knowledge_id"], note["revision_id"])
    with pytest.raises(BusinessError):
        pilot.search(actor, "배포", "project:test")
