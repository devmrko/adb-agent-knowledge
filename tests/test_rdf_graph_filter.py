from datetime import UTC, datetime
from uuid import uuid4

import pytest

from knowledge_app import shared_rdf


class Result:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class RecordingSession:
    def __init__(self, values):
        self.values, self.calls = values, []

    def execute(self, statement, parameters):
        self.calls.append((str(statement), parameters))
        return Result(self.values)


def test_graph_id_filter_preserves_owner_version_and_full_graph_validation():
    owner, version, claim = "a" * 64, str(uuid4()), str(uuid4())
    start = datetime.now(UTC)
    payload = {"predicate": "uses"}
    values = shared_rdf.rows(version, claim, payload, start)
    session = RecordingSession(values)
    shared_rdf.verify(session, owner, version, claim, payload, start, None)
    sql, params = session.calls[0]
    assert params == {"graph_uri": f"urn:vk:workflow:{owner}:{version}"}
    assert "r.G_ID IN" in sql
    assert "GET_MODEL" not in sql
    # The full selected graph must be checked, not only known/expected subjects.
    assert "WHERE r.START_NODE_ID" not in sql
    session.values = values + [("<unexpected>", "<predicate>", "<object>")]
    with pytest.raises(ValueError, match="mismatch"):
        shared_rdf.verify(session, owner, version, claim, payload, start, None)
    session.values = values[:-1]
    with pytest.raises(ValueError, match="mismatch"):
        shared_rdf.verify(session, owner, version, claim, payload, start, None)


def test_graph_overflow_is_not_hidden_by_set_comparison():
    owner, version, claim = "b" * 64, str(uuid4()), str(uuid4())
    start = datetime.now(UTC)
    values = shared_rdf.rows(version, claim, {}, start)
    session = RecordingSession((values * 151)[:301])
    with pytest.raises(ValueError, match="mismatch"):
        shared_rdf.verify(session, owner, version, claim, {}, start, None)


class NavigationSession(RecordingSession):
    def __init__(self, snapshot, values):
        super().__init__(values)
        self.snapshot = snapshot

    def get(self, model, identity):
        return self.snapshot


def test_navigation_native_graph_is_filtered_and_fully_verified():
    import json
    from types import SimpleNamespace

    from knowledge_app import navigation_rdf

    owner, snapshot_id = "c" * 64, str(uuid4())
    values = [("<subject>", "<urn:vk:navigation:member_of>", "<index>")]
    snapshot = SimpleNamespace(owner_id=owner, payload_json=json.dumps(values), native_stored=1)
    session = NavigationSession(snapshot, values)
    assert navigation_rdf.read(session, owner, snapshot_id)["status"] == "READY"
    sql, params = session.calls[0]
    assert params == {"graph_uri": f"urn:vk:workflow:{owner}:{snapshot_id}"}
    assert '"VK_FLOW_RDF#RDFM_VK_NAV"' in sql
    assert "r.G_ID IN" in sql
    assert "GET_MODEL" not in sql
    assert "1001 ROWS" in sql
    for invalid in [[], values + [("<unexpected>", "<p>", "<o>")], values * 1001]:
        session.values = invalid
        with pytest.raises(ValueError, match="mismatch"):
            navigation_rdf.read(session, owner, snapshot_id)
    session.calls.clear()
    assert navigation_rdf.read(session, "d" * 64, snapshot_id)["status"] == "NOT_INDEXED"
    assert not session.calls
