from types import SimpleNamespace

from fastapi.testclient import TestClient

from knowledge_app.audit_service import AuditService
from tests.test_agent_memory import client_app
from tests.test_browser_session import ORIGIN


def setup(tmp_path):
    app, store = client_app(tmp_path)
    store.relations = {}
    store.get_relation = lambda relation_id: store.relations.get(relation_id)

    def link_records(source, source_type, target, target_type, relation, relation_id, metadata):
        store.relations[relation_id] = SimpleNamespace(
            id=relation_id,
            source_record_id=source,
            target_record_id=target,
            relation_type=relation,
            metadata=metadata,
        )
        if relation in {"supersedes", "refines", "duplicates"}:
            store.rows[target_type, target].status = "invalid"
        return relation_id

    def list_relations(**kwargs):
        rows = list(store.relations.values())
        for key in ("source_record_id", "target_record_id"):
            if key in kwargs:
                rows = [r for r in rows if getattr(r, key) == kwargs[key]]
        return [r for r in rows if r.metadata["owner_id"] == kwargs["metadata_filter"]["owner_id"]][
            : kwargs["limit"]
        ]

    store.link_records, store.list_relations = link_records, list_relations
    return app, store


def save(c, key, scope="global"):
    return c.post(
        "/api/v1/agent-memory",
        json={"title": key, "text": "Oracle " + key, "scope": scope, "idempotency_key": key},
    ).json()["memory_id"]


def test_evidence_currentness_backlinks_outbox_and_isolation(tmp_path):
    app, store = setup(tmp_path)
    with TestClient(app, base_url=ORIGIN, headers={"Authorization": "Bearer alice"}) as c:
        memory = save(c, "memory")
        note = c.post(
            "/api/v1/knowledge", json={"title": "업무 근거", "text": "Oracle 실제 근거 문장"}
        ).json()
        assert app.state.service.process_one()
        evidence = {
            "memory_id": memory,
            "knowledge_id": note["knowledge_id"],
            "revision_id": note["revision_id"],
            "quote": "실제 근거 문장",
            "reason": "원문을 확인했다",
        }
        assert (
            c.post("/api/v1/agent-memory/evidence", json={**evidence, "quote": "없는 문장"}).status_code
            == 400
        )
        created = c.post("/api/v1/agent-memory/evidence", json=evidence)
        assert created.status_code == 200, created.text
        assert c.post("/api/v1/agent-memory/evidence", json=evidence).json()["reused"]
        refs = c.get("/api/v1/agent-memory/references", params={"memory_id": memory}).json()
        assert refs["items"][0]["status"] == "CURRENT"
        assert (
            c.get("/api/v1/agent-memory/references", params={"knowledge_id": note["knowledge_id"]}).json()[
                "items"
            ][0]["memory"]["id"]
            == memory
        )
        assert (
            c.get(
                "/api/v1/agent-memory/references",
                params={"memory_id": memory},
                headers={"Authorization": "Bearer bob"},
            ).status_code
            == 404
        )
        assert (
            c.post(
                "/api/v1/agent-memory/evidence", json=evidence, headers={"Authorization": "Bearer bob"}
            ).status_code
            == 404
        )
        assert c.get("/api/v1/agent-memory/" + memory + "/prepare-links").json()["writes_performed"] is False
        changed = c.post(
            "/api/v1/knowledge/" + note["knowledge_id"] + "/revisions",
            json={
                "text": "Oracle 새 근거 문장",
                "expected_revision_id": note["revision_id"],
                "change_note": "변경",
            },
        ).json()
        assert app.state.service.process_one()
        # Outbox has not run yet: read-time checks already catch stale evidence.
        refs = c.get("/api/v1/agent-memory/references", params={"memory_id": memory}).json()
        assert refs["items"][0]["status"] == "REVIEW_REQUIRED"
        audit = AuditService(app.state.service.factory)
        for _ in range(100):
            if not audit.process_one():
                break
        reviews = c.get("/api/v1/change-reviews").json()["items"]
        assert any(
            r["target_type"] == "MEMORY_EVIDENCE" and r["target_id"] == created.json()["id"] for r in reviews
        )
        new = c.post(
            "/api/v1/agent-memory/evidence",
            json={**evidence, "revision_id": changed["revision_id"], "quote": "새 근거 문장"},
        ).json()
        assert new["status"] == "CURRENT"
        refs = c.get("/api/v1/agent-memory/references", params={"memory_id": memory}).json()
        assert {r["status"] for r in refs["items"]} == {"CURRENT", "REVIEW_REQUIRED"}


def test_graph_cycles_bounds_history_scope_and_owner(tmp_path):
    app, store = setup(tmp_path)
    with TestClient(app, base_url=ORIGIN, headers={"Authorization": "Bearer alice"}) as c:
        a, b, d = save(c, "a"), save(c, "b"), save(c, "d", scope="project:else")

        def link(source, target, relation="supports"):
            return c.post(
                "/api/v1/agent-memory/links",
                json={
                    "source_id": source,
                    "target_id": target,
                    "relation": relation,
                    "reason": "검증된 연결",
                },
            )

        assert link(a, b, "supersedes").status_code == 200
        assert link(a, b, "supersedes").json()["reused"]
        assert link(b, a).status_code == 200
        assert link(a, d).status_code == 200
        assert link(a, a).status_code == 400
        graph = c.post("/api/v1/agent-memory/graph", json={"memory_id": a, "depth": 3}).json()
        assert len(graph["nodes"]) == 3 and len(graph["edges"]) == 3
        assert next(n for n in graph["nodes"] if n["id"] == b)["status"] == "invalid"
        limited = c.post("/api/v1/agent-memory/graph", json={"memory_id": a, "max_edges": 1}).json()
        assert len(limited["edges"]) == 1 and limited["truncated"]
        scoped = c.post("/api/v1/agent-memory/graph", json={"memory_id": a, "scopes": ["global"]}).json()
        assert d not in [n["id"] for n in scoped["nodes"]]
        assert (
            c.post(
                "/api/v1/agent-memory/graph", json={"memory_id": a}, headers={"Authorization": "Bearer bob"}
            ).status_code
            == 404
        )
        # Even malicious SDK relations cannot leak another owner's endpoint.
        c.headers["Authorization"] = "Bearer bob"
        alien = save(c, "alien")
        c.headers["Authorization"] = "Bearer alice"
        assert link(a, alien).status_code == 404
        valid = next(iter(store.relations.values()))
        store.relations["poison"] = SimpleNamespace(
            id="poison",
            source_record_id=a,
            target_record_id=alien,
            relation_type="supports",
            metadata=valid.metadata,
        )
        safe = c.post("/api/v1/agent-memory/graph", json={"memory_id": a}).json()
        assert alien not in [n["id"] for n in safe["nodes"]]


def test_unified_recall_is_scoped_and_reports_partial_failure(tmp_path, monkeypatch):
    from knowledge_app.navigation import NavigationService

    async def navigation(self, actor, command, **kwargs):
        return {"items": [], "plan": {"graph": True}}

    monkeypatch.setattr(NavigationService, "execute", navigation)
    app, store = setup(tmp_path)
    with TestClient(app, base_url=ORIGIN, headers={"Authorization": "Bearer alice"}) as c:
        mid = save(c, "retrieval", scope="project:one")
        result = c.post("/api/v1/knowledge/recall", json={"text": "Oracle", "scopes": ["project:one"]}).json()
        item = result["agent_memories"]["items"][0]
        assert item["memory_id"] == mid and "references" in item and "graph" in item
        empty = c.post(
            "/api/v1/knowledge/recall", json={"text": "Oracle", "scopes": ["project:other"]}
        ).json()
        assert empty["agent_memories"]["items"] == []
        sensitive = c.post(
            "/api/v1/knowledge/recall", json={"text": "Oracle", "contains_sensitive": True}
        ).json()
        assert "agent_memories" not in sensitive

        def broken(*args, **kwargs):
            raise RuntimeError("secret provider")

        store.search = broken
        partial = c.post("/api/v1/knowledge/recall", json={"text": "Oracle"}).json()
        assert partial["items"] == []
        assert partial["agent_memories"]["scopes"][0]["status"] == "UNAVAILABLE"
        assert "secret" not in str(partial)
