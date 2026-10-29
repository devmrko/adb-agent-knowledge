import json
from uuid import uuid4

import httpx
import pytest
from test_knowledge import knowledge as knowledge_fixture  # noqa: F401

from knowledge_app.graph_service import GraphService
from knowledge_app.indexes import IndexService
from knowledge_app.navigation import NavigationService
from knowledge_app.routing import MemoryRouter, RoutingSettings


def source(client, service, text="Oracle 접속 오류를 해결했다. Wallet 설정을 확인했다.", **extra):
    res = client.post("/api/v1/knowledge", json={"title": "접속 기록", "text": text, **extra})
    assert res.status_code == 202, res.text
    data = res.json()
    assert service.process_one()
    return data


def index(client, key="oracle", scope="global"):
    body = {"key": key, "title": key, "summary": "Oracle 접속 및 운영 기록", "scope": scope}
    res = client.post("/api/v1/indexes", json=body)
    assert res.status_code == 200, res.text
    return res.json()


def link(client, idx, kid, **extra):
    res = client.put(
        f"/api/v1/indexes/{idx['id']}/entries", json={"knowledge_id": kid, "verified": True, **extra}
    )
    assert res.status_code == 200, res.text
    return res.json()


def test_summary_revision_binding_and_no_stale_inheritance(knowledge_fixture):  # noqa: F811
    c, s, _ = knowledge_fixture
    first = source(c, s, summary="Wallet 설정을 확인해 접속 오류를 해결함.", edit_origin="HUMAN")
    root = f"/api/v1/knowledge/{first['knowledge_id']}"
    preview = c.get(f"{root}/revisions/{first['revision_id']}/summary").json()
    assert preview["summary_kind"] == "HUMAN" and preview["summary_persisted"]
    assert c.get(root + "/references").json()["rdf"]["status"] == "READY"
    next = c.post(
        root + "/revisions",
        json={
            "expected_revision_id": first["revision_id"],
            "text": "Oracle 접속은 방화벽을 수정하여 해결했다.",
        },
    ).json()
    assert s.process_one()
    latest = c.get(f"{root}/revisions/{next['revision_id']}/summary").json()
    assert (
        latest["summary_kind"] == "EXTRACTIVE"
        and "방화벽" in latest["summary"]
        and "Wallet" not in latest["summary"]
    )
    assert c.get(f"{root}/revisions/{first['revision_id']}/summary").json() == preview
    assert (
        c.post("/api/v1/knowledge", json={"title": "빈 요약", "text": "원문", "summary": "   "}).status_code
        == 400
    )
    found = c.post("/api/v1/knowledge/search", json={"query": "Oracle"}).json()["items"][0]
    assert found["summary_revision_id"] == next["revision_id"]


def test_multiple_indexes_paging_dynamic_summary_and_backlinks(knowledge_fixture):  # noqa: F811
    c, s, _ = knowledge_fixture
    notes = [source(c, s, summary=f"요약 {n}") for n in range(3)]
    a, b = index(c), index(c, "project-records")
    for n, k in enumerate(notes):
        link(c, a, k["knowledge_id"], position=n)
    link(c, b, notes[0]["knowledge_id"])
    assert link(c, b, notes[0]["knowledge_id"])["unchanged"]
    page = c.get(f"/api/v1/indexes/{a['id']}/entries?limit=2").json()
    assert len(page["items"]) == 2 and page["next_offset"] == 2
    assert len(c.get(f"/api/v1/indexes/{a['id']}/entries?offset=2&limit=2").json()["items"]) == 1
    root = "/api/v1/knowledge/" + notes[0]["knowledge_id"]
    refs = c.get(root + "/references").json()
    assert len(refs["indexes"]) == 2 and refs["rdf"]["status"] == "READY"
    assert refs["indexes"][0]["rdf"]["edges"][0]["relation"] == "member_of"
    revision = c.post(
        root + "/revisions",
        json={
            "text": "Oracle 상세 보완",
            "summary": "새 요약",
            "expected_revision_id": notes[0]["revision_id"],
        },
    ).json()
    assert s.process_one()
    for idx in [a, b]:
        items = c.get(f"/api/v1/indexes/{idx['id']}/entries").json()["items"]
        card = next(i for i in items if i["knowledge_id"] == notes[0]["knowledge_id"])
        assert card["summary"] == "새 요약" and card["revision_id"] == revision["revision_id"]
    c.post(root + "/retire", json={"reason": "사용자 폐기"})
    assert len(c.get(f"/api/v1/indexes/{b['id']}/entries").json()["items"]) == 0
    assert c.get("/api/v1/indexes/unfiled").json()["items"] == []


def test_index_scope_owner_original_and_history_boundaries(knowledge_fixture):  # noqa: F811
    c, s, _ = knowledge_fixture
    a = index(c, "a", "project:a")
    b = source(
        c,
        s,
        scope="project:b",
        sources=[{"kind": "local_file", "location": "/notes/test.md", "machine_id": "machine-a"}],
    )
    assert (
        c.put(
            f"/api/v1/indexes/{a['id']}/entries", json={"knowledge_id": b["knowledge_id"], "verified": True}
        ).status_code
        == 404
    )
    global_index = index(c)
    link(c, global_index, b["knowledge_id"])
    assert not c.get(f"/api/v1/indexes/{global_index['id']}/entries?scope=project:a").json()["items"]
    root = "/api/v1/knowledge/" + b["knowledge_id"]
    refs = c.get(root + "/references").json()
    assert refs["sources"][0]["availability"] == "not_checked"
    assert c.get(refs["original_uri"]).content.decode().startswith("Oracle")
    c.headers["Authorization"] = "Bearer bob"
    assert c.get(root + "/references").status_code == 404
    assert c.get(refs["original_uri"]).status_code == 404
    assert c.get(f"/api/v1/indexes/{global_index['id']}/history").status_code == 404
    assert c.get("/api/v1/indexes").json()["items"] == []


def test_index_conflicts_history_and_unfiled(knowledge_fixture):  # noqa: F811
    c, s, _ = knowledge_fixture
    note = source(c, s)
    idx = index(c)
    assert len(c.get("/api/v1/indexes/unfiled").json()["items"]) == 1
    linked = link(c, idx, note["knowledge_id"])
    assert not c.get("/api/v1/indexes/unfiled").json()["items"]
    body = {k: idx[k] for k in ["key", "title", "summary", "body", "scope"]}
    body.update(title="새 제목", expected_version=idx["version"])
    assert c.put("/api/v1/indexes/" + idx["id"], json=body).status_code == 409
    body["expected_version"] = linked["version"]
    assert c.put("/api/v1/indexes/" + idx["id"], json=body).status_code == 200
    history = c.get("/api/v1/indexes/" + idx["id"] + "/history").json()["changes"]
    assert [i["operation"] for i in history] == ["document", "member", "document"]


def route_service(service, scores=None, broken=False):
    def handler(request):
        if broken:
            return httpx.Response(503)
        data = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "answers": {
                    k: {"type": "noul", "noul": (scores or {}).get(k, 0.1)} for k in data["questions"]
                }
            },
        )

    router = MemoryRouter(RoutingSettings(_env_file=None), transport=httpx.MockTransport(handler))
    return NavigationService(
        service, IndexService(service.factory), GraphService(service.factory, service.settings), router
    )


@pytest.mark.parametrize(
    "scores,route",
    [
        ({"direct": 0.8, "index": 0.1}, "direct"),
        ({"direct": 0.1, "index": 0.8, "i0": 0.8}, "index"),
        ({"direct": 0.8, "index": 0.8, "i0": 0.8}, "both"),
    ],
)
def test_kev_routes_catalog_and_summary_previews(knowledge_fixture, scores, route):  # noqa: F811
    import asyncio

    from test_knowledge import TestVerifier

    from knowledge_app.navigation import NavigationRequest

    c, s, _ = knowledge_fixture
    note = source(c, s, summary="접속 요약")
    idx = index(c)
    link(c, idx, note["knowledge_id"])
    nav = route_service(s, scores)
    result = asyncio.run(
        nav.execute(TestVerifier().verify("alice"), NavigationRequest(text="Oracle", scopes=["global"]))
    )
    assert result["plan"]["route"] == route
    assert result["items"] or result["indexes"]
    assert all("matches" not in i for i in result["items"])
    assert result["navigation_complete"] is False


def test_router_failure_fallback_and_save_guards(knowledge_fixture):  # noqa: F811
    import asyncio

    from test_knowledge import TestVerifier

    from knowledge_app.navigation import NavigationRequest

    c, s, _ = knowledge_fixture
    source(c, s)
    idx = index(c)
    nav = route_service(s, broken=True)
    actor = TestVerifier().verify("alice")
    result = asyncio.run(nav.execute(actor, NavigationRequest(text="Oracle")))
    assert result["plan"]["route"] == "agent_review" and result["items"]
    result = asyncio.run(
        nav.execute(actor, NavigationRequest(text="Oracle", mode="index", index_ids=[idx["id"]]))
    )
    assert result["items"] and "index_empty_use_direct" in result["fallbacks"]
    for request in [
        NavigationRequest(text="secret", contains_sensitive=True),
        NavigationRequest(text="fact", verified=False),
        NavigationRequest(text="fact", verified=True, storage_allowed=False),
    ]:
        result = asyncio.run(nav.execute(actor, request, save=True))
        assert not result["items"] and not result["writes_performed"]
    result = asyncio.run(
        nav.execute(actor, NavigationRequest(text="Oracle", verified=True, explicit_request=True), save=True)
    )
    assert result["items"] and not result["writes_performed"]


def test_original_and_summary_wrong_revision(knowledge_fixture):  # noqa: F811
    c, s, _ = knowledge_fixture
    a = source(c, s)
    b = source(c, s)
    for kind in ["summary", "original"]:
        assert (
            c.get(f"/api/v1/knowledge/{a['knowledge_id']}/revisions/{b['revision_id']}/{kind}").status_code
            == 404
        )
    assert c.get(f"/api/v1/knowledge/{a['knowledge_id']}/references?revision_id={uuid4()}").status_code == 404


def test_refresh_derived_preserves_source_and_authored_summary(knowledge_fixture):  # noqa: F811
    c, s, _ = knowledge_fixture
    note = source(c, s, summary="사용자 요약", edit_origin="HUMAN")
    root = "/api/v1/knowledge/" + note["knowledge_id"]
    before = c.get(root + "/history").json()
    for _ in range(2):
        response = c.post(root + "/refresh-derived")
        assert response.status_code == 200
        assert response.json()["summary"] == "사용자 요약"
        assert response.json()["revision_id"] == note["revision_id"]
    assert c.get(root + "/history").json() == before
    c.headers["Authorization"] = "Bearer bob"
    assert c.post(root + "/refresh-derived").status_code == 404


def test_recall_graph_uses_exact_search_revisions(knowledge_fixture, monkeypatch):  # noqa: F811
    import asyncio

    from test_knowledge import TestVerifier

    from knowledge_app.navigation import NavigationRequest

    c, s, _ = knowledge_fixture
    note = source(c, s)
    nav = route_service(s, {"direct": 0.8, "graph": 0.9})
    received = []

    def capture(actor, request):
        received.append(request)
        return {"status": "READY", "edges": [], "nodes": []}

    monkeypatch.setattr(nav.graph, "search", capture)
    result = asyncio.run(nav.execute(TestVerifier().verify("alice"), NavigationRequest(text="Oracle")))
    assert result["graph"]["status"] == "READY"
    assert received[0].query == "Oracle"
    assert received[0].include_entity_matches
    assert str(received[0].seed_revisions[0].revision_id) == note["revision_id"]
