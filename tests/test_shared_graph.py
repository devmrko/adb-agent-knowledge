from datetime import UTC, datetime, timedelta

import pytest
from test_knowledge import knowledge as knowledge_fixture  # noqa: F401

from knowledge_app import graph_service


def source(client, service, text="A는 B를 사용한다. 2026년부터 적용.", scope="global"):
    data = client.post("/api/v1/knowledge", json={"title": "관계 근거", "text": text, "scope": scope}).json()
    assert service.process_one()
    return {"knowledge_id": data["knowledge_id"], "revision_id": data["revision_id"], "quote": text}


def entity(client, key, scope="global", label=None):
    response = client.post(
        "/api/v1/graph/entities", json={"identity_key": key, "label": label or key, "scope": scope}
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


def setup(knowledge):
    client, service, _ = knowledge
    service.settings.workflow_rdf_enabled = True
    evidence = source(client, service)
    body = {
        "subject_id": entity(client, "A"),
        "object_id": entity(client, "B"),
        "predicate": "uses",
        "verified": True,
        "evidence": [evidence],
    }
    return client, service, body


def put(client, body, path="/api/v1/graph/assertions", method="post"):
    response = getattr(client, method)(path, json=body)
    assert response.status_code == 200, response.text
    return response.json()


def search(client, **kwargs):
    return put(client, kwargs, "/api/v1/graph/search")


def test_shared_identity_dedup_and_evidence_lifecycle(knowledge_fixture):  # noqa: F811
    client, service, body = setup(knowledge_fixture)
    assert entity(client, "A") == body["subject_id"]
    assert entity(client, "other-A", label="A") != body["subject_id"]
    first = put(client, body)
    assert put(client, body)["unchanged"]
    another = source(client, service)
    supplement = put(client, {**body, "evidence": [another]})
    assert supplement["assertion_id"] == first["assertion_id"]
    assert supplement["version_id"] != first["version_id"]
    assert len(search(client, query="A")["edges"][0]["evidence"]) == 2
    client.post(
        "/api/v1/knowledge/" + body["evidence"][0]["knowledge_id"] + "/retire", json={"reason": "사용자 폐기"}
    )
    assert len(search(client)["edges"][0]["evidence"]) == 1
    client.post("/api/v1/knowledge/" + another["knowledge_id"] + "/retire", json={"reason": "사용자 폐기"})
    assert search(client)["edges"] == []
    assert (
        len(client.get("/api/v1/graph/assertions/" + first["assertion_id"] + "/history").json()["versions"])
        == 2
    )


def test_bitemporal_correction_and_half_open_interval(knowledge_fixture, monkeypatch):  # noqa: F811
    client, _, body = setup(knowledge_fixture)
    t1 = datetime.now(UTC) + timedelta(seconds=1)
    t2 = t1 + timedelta(days=1)
    monkeypatch.setattr(graph_service, "now", lambda: t1)
    body.update(
        temporal_kind="INTERVAL",
        valid_from="2026-01-01T00:00:00Z",
        valid_to="2027-01-01T00:00:00Z",
        temporal_basis={"text": body["evidence"][0]["quote"]},
    )
    first = put(client, body)
    assert len(search(client, valid_at="2026-06-01T00:00:00Z")["edges"]) == 1
    assert search(client, valid_at="2027-01-01T00:00:00Z")["edges"] == []
    monkeypatch.setattr(graph_service, "now", lambda: t2)
    revision = {
        **body,
        "valid_from": "2026-03-01T00:00:00Z",
        "expected_version_id": first["version_id"],
        "change_note": "시작 시점 정정",
    }
    path = "/api/v1/graph/assertions/" + first["assertion_id"]
    corrected = put(client, revision, path, "put")
    assert corrected["version_id"] != first["version_id"]
    assert search(client, valid_at="2026-02-01T00:00:00Z")["edges"] == []
    past = search(client, valid_at="2026-02-01T00:00:00Z", known_at=t1.isoformat())
    assert past["edges"][0]["version_id"] == first["version_id"]
    assert search(client, known_at=(t1 - timedelta(microseconds=1)).isoformat())["edges"] == []
    assert client.put(path, json=revision).status_code == 409
    history = client.get(path + "/history").json()["versions"]
    assert history[0]["recorded_to"] == t2.isoformat()


def test_unknown_dates_and_temporal_validation(knowledge_fixture):  # noqa: F811
    client, _, body = setup(knowledge_fixture)
    put(client, body)
    assert len(search(client)["edges"]) == 1
    assert search(client, valid_at="2026-06-01T00:00:00Z")["edges"] == []
    assert len(search(client, valid_at="2026-06-01T00:00:00Z", include_undated=True)["edges"]) == 1
    for changes in (
        {"temporal_kind": "TIMELESS"},
        {"temporal_kind": "INTERVAL"},
        {"valid_from": "2026-01-01"},
        {"verified": False},
    ):
        assert client.post("/api/v1/graph/assertions", json={**body, **changes}).status_code == 400
    assert client.post("/api/v1/graph/search", json={"known_at": "2026-01-01"}).status_code == 400
    assert (
        client.post(
            "/api/v1/graph/assertions",
            json={**body, "temporal_kind": "TIMELESS", "temporal_basis": {"text": "없는 근거"}},
        ).status_code
        == 400
    )


def test_cross_project_expansion_owner_and_scope_boundaries(knowledge_fixture):  # noqa: F811
    client, service, _ = knowledge_fixture
    service.settings.workflow_rdf_enabled = True
    a = entity(client, "A", "project:a")
    b = entity(client, "B", "project:b")
    db = entity(client, "DB")
    ea = source(client, service, scope="project:a")
    eb = source(client, service, scope="project:b")
    ab = put(
        client,
        {"subject_id": a, "object_id": b, "predicate": "depends_on", "evidence": [ea], "verified": True},
    )
    put(client, {"subject_id": b, "object_id": db, "predicate": "uses", "evidence": [eb], "verified": True})
    assert len(search(client, query="A", scopes=["project:a", "project:b"])["edges"]) == 2
    assert search(client, entity_ids=[a], scopes=["project:a"])["edges"] == []
    assert len(search(client, entity_ids=[b], scopes=["project:b"])["edges"]) == 1
    assert search(client, query="없는 이름")["edges"] == []
    client.headers["Authorization"] = "Bearer bob"
    assert search(client)["edges"] == []
    assert client.get("/api/v1/graph/assertions/" + ab["assertion_id"] + "/history").status_code == 404
    assert (
        client.post(
            "/api/v1/graph/assertions",
            json={"subject_id": a, "object_id": b, "predicate": "uses", "evidence": [ea], "verified": True},
        ).status_code
        == 404
    )


def test_source_revision_and_retraction_history(knowledge_fixture):  # noqa: F811
    client, service, body = setup(knowledge_fixture)
    first = put(client, body)
    captured = datetime.now(UTC).isoformat()
    evidence = body["evidence"][0]
    client.post(
        "/api/v1/knowledge/" + evidence["knowledge_id"] + "/revisions",
        json={"expected_revision_id": evidence["revision_id"], "text": "A는 C를 사용한다."},
    )
    assert service.process_one()
    assert search(client)["edges"] == []
    assert search(client, known_at=captured)["edges"][0]["version_id"] == first["version_id"]
    # A separate still-current source allows explicit retirement of the assertion.
    new_source = source(client, service)
    revised = {
        **body,
        "evidence": [new_source],
        "expected_version_id": first["version_id"],
        "status": "RETRACTED",
    }
    put(client, revised, "/api/v1/graph/assertions/" + first["assertion_id"], "put")
    assert search(client)["edges"] == []
    assert search(client, known_at=captured)["edges"]


def test_literal_and_grounding(knowledge_fixture):  # noqa: F811
    client, _, body = setup(knowledge_fixture)
    body.pop("object_id")
    body["literal"] = "2026년부터 적용"
    put(client, body)
    result = search(client)
    assert any(n["kind"] == "literal" for n in result["nodes"])
    bad = {**body, "evidence": [{**body["evidence"][0], "quote": "원문에 없는 문장"}]}
    assert client.post("/api/v1/graph/assertions", json=bad).status_code == 400


def test_native_oracle_literal_roundtrip_with_unescaped_quotes():
    import json
    from uuid import uuid4

    from knowledge_app import shared_rdf

    version, claim = str(uuid4()), str(uuid4())
    payload = {
        "literal": '따옴표 "원문"\n경로 \\n',
        "temporal_basis": {"text": '"기간"', "user_asserted": False},
        "verified": True,
    }
    start = datetime.now(UTC)
    encoded = shared_rdf.rows(version, claim, payload, start)
    actual = [(s, p, '"' + json.loads(o) + '"' if o.startswith('"') else o) for s, p, o in encoded]

    class Result:
        def all(self):
            return actual

    class Session:
        def execute(self, statement, parameters):
            return Result()

    shared_rdf.verify(Session(), "0" * 64, version, claim, payload, start, None)
    actual.pop()
    with pytest.raises(ValueError):
        shared_rdf.verify(Session(), "0" * 64, version, claim, payload, start, None)


def test_connected_note_filter_before_pagination_and_search(knowledge_fixture):  # noqa: F811
    client, service, body = setup(knowledge_fixture)
    connected = body["evidence"][0]["knowledge_id"]
    first = put(client, body)
    # Multiple relationships must not duplicate the knowledge row.
    put(client, {**body, "predicate": "depends_on"})
    source(client, service, text="A는 B를 사용한다. 아직 연결이 없는 새 노트.")
    page = client.get("/api/v1/knowledge", params={"has_relations": True, "limit": 1}).json()
    assert [i["knowledge_id"] for i in page["items"]] == [connected]
    assert client.get("/api/v1/knowledge", params={"has_relations": True, "offset": 1}).json()["items"] == []
    assert (
        client.get("/api/v1/knowledge", params={"has_relations": True, "category": "absent"}).json()["items"]
        == []
    )
    result = client.post(
        "/api/v1/knowledge/search",
        json={"query": "A B", "has_relations": True, "min_similarity": 0},
    )
    assert result.status_code == 200, result.text
    assert result.json()["items"]
    assert {i["knowledge_id"] for i in result.json()["items"]} == {connected}
    history = client.get(f"/api/v1/graph/assertions/{first['assertion_id']}/history").json()
    version = next(v for v in history["versions"] if v["recorded_to"] is None)
    version_id = version.pop("version_id")
    version.pop("recorded_from")
    version.pop("recorded_to")
    put(
        client,
        {**version, "expected_version_id": version_id, "status": "RETRACTED"},
        f"/api/v1/graph/assertions/{first['assertion_id']}",
        "put",
    )
    # The second active relationship still qualifies.
    assert len(client.get("/api/v1/knowledge", params={"has_relations": True}).json()["items"]) == 1


def test_connected_filter_excludes_retracted_and_old_source(knowledge_fixture):  # noqa: F811
    client, service, body = setup(knowledge_fixture)
    first = put(client, body)
    history = client.get(f"/api/v1/graph/assertions/{first['assertion_id']}/history").json()
    version = next(v for v in history["versions"] if v["recorded_to"] is None)
    version_id = version.pop("version_id")
    version.pop("recorded_from")
    version.pop("recorded_to")
    put(
        client,
        {**version, "expected_version_id": version_id, "status": "RETRACTED"},
        f"/api/v1/graph/assertions/{first['assertion_id']}",
        "put",
    )
    assert client.get("/api/v1/knowledge", params={"has_relations": True}).json()["items"] == []
    put(client, {**body, "predicate": "depends_on"})
    from sqlalchemy import select

    from knowledge_app.models import Item

    with service.factory() as session:
        item = session.scalar(select(Item).where(Item.id == body["evidence"][0]["knowledge_id"]))
        item.active_revision_id = None
        session.commit()
    assert client.get("/api/v1/knowledge", params={"has_relations": True}).json()["items"] == []


def test_revision_seed_expands_shared_entities_and_excludes_unrelated(knowledge_fixture):  # noqa: F811
    client, service, body = setup(knowledge_fixture)
    first = put(client, body)
    second_evidence = source(client, service, "B는 C를 사용한다.")
    second = put(
        client,
        {
            **body,
            "subject_id": body["object_id"],
            "object_id": entity(client, "C"),
            "evidence": [second_evidence],
        },
    )
    other = put(
        client,
        {
            **body,
            "subject_id": entity(client, "X"),
            "object_id": entity(client, "Y"),
            "evidence": [source(client, service, "X는 Y를 사용한다.")],
        },
    )
    seed = {k: body["evidence"][0][k] for k in ("knowledge_id", "revision_id")}
    result = search(client, seed_revisions=[seed], depth=1)
    levels = {e["assertion_id"]: e["retrieval_level"] for e in result["edges"]}
    assert levels == {first["assertion_id"]: 0, second["assertion_id"]: 1}
    assert other["assertion_id"] not in levels
    assert search(client, seed_revisions=[seed], depth=0)["edges"][0]["assertion_id"] == first["assertion_id"]
    assert (
        search(client, seed_revisions=[{**seed, "revision_id": second_evidence["revision_id"]}])["edges"]
        == []
    )
    assert (
        client.post("/api/v1/graph/search", json={"seed_revisions": [seed], "query": "A"}).status_code == 400
    )


def test_revision_seed_cannot_use_retired_evidence_to_reach_valid_other_source(knowledge_fixture):  # noqa: F811
    client, service, body = setup(knowledge_fixture)
    put(client, body)
    extra = source(client, service)
    put(client, {**body, "evidence": [extra]})
    seed = {k: body["evidence"][0][k] for k in ("knowledge_id", "revision_id")}
    client.post("/api/v1/knowledge/" + seed["knowledge_id"] + "/retire", json={"reason": "사용자 폐기"})
    assert search(client, seed_revisions=[seed])["edges"] == []
    assert len(search(client, query="A")["edges"]) == 1


def test_combined_entity_and_source_lanes_with_paths(knowledge_fixture):  # noqa: F811
    client, service, body = setup(knowledge_fixture)
    ab = put(client, body)
    c = entity(client, "Cafesto")
    d = entity(client, "Foundation")
    extra = source(client, service, "Cafesto uses Foundation")
    cd = put(client, {**body, "subject_id": c, "object_id": d, "evidence": [extra]})
    seed = {k: body["evidence"][0][k] for k in ("knowledge_id", "revision_id")}
    result = search(client, query="Cafesto", seed_revisions=[seed], include_entity_matches=True)
    assert {e["assertion_id"] for e in result["edges"]} == {ab["assertion_id"], cd["assertion_id"]}
    assert result["retrieval_lanes"] == ["source", "entity"]
    assert len(result["related_knowledge"]) == 2
    assert result["paths"]
    versions = {e["version_id"] for e in result["edges"]}
    assert all(set(p["version_ids"]) <= versions for p in result["paths"])
    bounded = search(client, query="Cafesto", seed_revisions=[seed], include_entity_matches=True, max_edges=1)
    assert len(bounded["edges"]) == 1 and bounded["truncated"]
    assert all(set(p["version_ids"]) <= {bounded["edges"][0]["version_id"]} for p in bounded["paths"])
    client.headers["Authorization"] = "Bearer bob"
    assert search(client, query="Cafesto", seed_revisions=[seed], include_entity_matches=True)["edges"] == []


def test_direction_predicates_and_multihop_paths(knowledge_fixture):  # noqa: F811
    client, service, body = setup(knowledge_fixture)
    put(client, body)
    c = entity(client, "C")
    evidence = source(client, service, "B depends on C")
    put(
        client,
        {
            **body,
            "subject_id": body["object_id"],
            "object_id": c,
            "predicate": "depends_on",
            "evidence": [evidence],
        },
    )
    result = search(client, entity_ids=[body["subject_id"]], direction="outgoing", depth=1)
    assert len(result["edges"]) == 2
    assert any(p["entity_ids"] == [body["subject_id"], body["object_id"], c] for p in result["paths"])
    assert search(client, entity_ids=[body["subject_id"]], direction="incoming")["edges"] == []
    assert len(search(client, entity_ids=[body["subject_id"]], predicates=["uses"])["edges"]) == 1
    assert len(search(client, entity_ids=[c], direction="incoming", depth=1)["edges"]) == 2


def test_search_returns_graph_and_source_updates_remove_old_evidence(knowledge_fixture):  # noqa: F811
    client, service, body = setup(knowledge_fixture)
    put(client, body)
    first = body["evidence"][0]
    other = source(client, service)
    put(client, {**body, "evidence": [other]})
    response = client.post("/api/v1/knowledge/search", json={"query": "A", "include_graph": True})
    assert response.status_code == 200, response.text
    assert len(response.json()["graph"]["edges"][0]["evidence"]) == 2
    updated = client.post(
        f"/api/v1/knowledge/{first['knowledge_id']}/revisions",
        json={"expected_revision_id": first["revision_id"], "text": "A no longer uses B"},
    )
    assert updated.status_code == 202
    assert service.process_one()
    result = search(client, query="A")
    assert [e["knowledge_id"] for e in result["edges"][0]["evidence"]] == [other["knowledge_id"]]
    client.post(f"/api/v1/knowledge/{other['knowledge_id']}/retire", json={"reason": "retire"})
    result = search(client, query="A")
    assert result["edges"] == [] and result["related_knowledge"] == [] and result["paths"] == []


def test_recall_explicit_graph_without_router_selection(knowledge_fixture):  # noqa: F811
    client, _, body = setup(knowledge_fixture)
    put(client, body)
    response = client.post(
        "/api/v1/knowledge/recall", json={"text": "A", "mode": "direct", "graph_mode": "always"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["graph"]["edges"]
    hidden = client.post(
        "/api/v1/knowledge/recall", json={"text": "A", "mode": "direct", "graph_mode": "never"}
    ).json()
    assert "graph" not in hidden
