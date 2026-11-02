from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from knowledge_app.agent_memory_contracts import MemoryQuery, MemorySave, ProfileSave
from knowledge_app.agent_memory_service import locks, owner_id
from tests.test_browser_session import ORIGIN, login, make_app


class Store:
    def __init__(self):
        self.rows = {}

    def get(self, typ, key):
        return self.rows.get((typ, key))

    def list(self, typ, **kwargs):
        rows = [r for (t, _), r in self.rows.items() if t == typ]
        for key in ("user_id", "agent_id"):
            if key in kwargs:
                rows = [r for r in rows if getattr(r, key, None) == kwargs[key]]
        for key, value in kwargs.get("metadata_filter", {}).items():
            rows = [r for r in rows if r.metadata.get(key) == value]
        return rows[: kwargs.get("limit", 100)]

    def update(self, typ, key, **kwargs):
        row = self.rows[typ, key]
        for k, v in kwargs.items():
            setattr(row, k, v)

    def put(self, typ, key, content="", **kwargs):
        self.rows[typ, key] = SimpleNamespace(
            id=key,
            content=content,
            timestamp="2026-11-02",
            metadata=kwargs.get("metadata", {}),
            user_id=kwargs.get("user_id"),
            agent_id=kwargs.get("agent_id"),
            status="valid",
        )
        return key

    def add_agent(self, key, content, **kwargs):
        return self.put("agent_profile", key, content, **kwargs)

    def add_user(self, key, content, **kwargs):
        return self.put("user_profile", key, content, **kwargs)

    def create_thread(self, thread_id, **kwargs):
        return self.put("thread", thread_id, **kwargs)

    def add_memory(self, content, memory_type, memory_id, **kwargs):
        return self.put(memory_type, memory_id, content, **kwargs)

    def search(self, query, **kwargs):
        return [
            SimpleNamespace(record=r)
            for typ in ("memory", "fact", "preference", "guideline")
            for r in self.list(typ, **kwargs)
        ]


def client_app(tmp_path):
    app = make_app(tmp_path, agent_memory_enabled=True)
    store = Store()
    app.state.agent_memory.repo = SimpleNamespace(store=store, client=store)
    locks.create(app.state.engine)
    return app, store


def test_memory_auth_idempotency_and_profiles(tmp_path):
    app, store = client_app(tmp_path)
    with TestClient(app, base_url=ORIGIN) as c:
        path = "/api/v1/agent-memory"
        assert c.post(path + "/search", json={}).status_code == 401
        csrf = login(c).json()["csrf"]
        headers = {"Origin": ORIGIN, "X-CSRF-TOKEN": csrf}
        profile = {"kind": "agent", "key": "codex-tasteby", "name": "Tasteby 운영 도우미"}
        assert c.post(path + "/profiles", json=profile).status_code == 403
        agent = c.post(path + "/profiles", json=profile, headers=headers).json()
        assert agent["version"] == 1
        assert c.post(path + "/profiles", json=profile, headers=headers).status_code == 409
        updated = c.post(
            path + "/profiles",
            json={**profile, "name": "Tasteby 개발 도우미", "expected_version": 1},
            headers=headers,
        ).json()
        assert updated["id"] == agent["id"] and updated["version"] == 2
        thread = c.post(
            path + "/profiles",
            json={"kind": "thread", "key": "task-1", "name": "로그인 개선", "agent_id": agent["id"]},
            headers=headers,
        ).json()
        command = {
            "title": "로그인 점검 경험",
            "text": "검증된 세션 설정 점검",
            "agent_id": agent["id"],
            "origin_thread_id": thread["id"],
            "idempotency_key": "save1",
        }
        saved = c.post(path, json=command, headers=headers)
        assert saved.status_code == 200
        assert saved.json()["status"] == "READY"
        assert c.post(path, json=command, headers=headers).json()["reused"] is True
        assert c.post(path, json={**command, "text": "다른 본문"}, headers=headers).status_code == 409
        result = c.post(path + "/search", json={}, headers=headers).json()
        assert len(result["items"]) == 1
        assert result["items"][0]["agent_name"] == "Tasteby 개발 도우미"
        assert result["items"][0]["thread_name"] == "로그인 개선"
        bob = {"Authorization": "Bearer bob"}
        assert c.post(path + "/search", json={}, headers=bob).json()["items"] == []
        assert c.get(path + "/profiles", headers=bob).json()["items"] == []
        assert c.post(path, json={**command, "idempotency_key": "bob"}, headers=bob).status_code == 404
        assert c.post(path + "/search", json={"agent_id": agent["id"]}, headers=bob).status_code == 404
        assert c.post(path, json={**command, "user_id": "forged"}, headers=headers).status_code == 400
        assert (
            c.post(path + "/search", json={}, headers={"Origin": ORIGIN, "X-CSRF-TOKEN": "wrong"}).status_code
            == 403
        )


def test_disabled_and_safe_failure(tmp_path):
    with TestClient(make_app(tmp_path), base_url=ORIGIN) as c:
        h = {"Authorization": "Bearer alice"}
        result = c.post("/api/v1/agent-memory/search", json={}, headers=h)
        assert result.status_code == 200 and result.json()["status"] == "NOT_CONFIGURED"
    app, store = client_app(tmp_path)

    def broken(*args, **kwargs):
        raise RuntimeError("secret SQL password")

    store.list = broken
    with TestClient(app, base_url=ORIGIN) as c:
        result = c.post("/api/v1/agent-memory/search", json={}, headers={"Authorization": "Bearer alice"})
        assert result.status_code == 503
        assert "secret" not in result.text and "password" not in result.text


def test_metadata_preserved_and_current_filter(tmp_path):
    app, store = client_app(tmp_path)
    from python_foundation.security import Actor

    actor = Actor("test", "alice", frozenset())
    svc = app.state.agent_memory
    p = svc.save_profile(ProfileSave(kind="agent", key="one", name="첫 이름"), actor)
    store.rows["agent_profile", p["id"]].metadata["custom"] = "keep"
    svc.save_profile(ProfileSave(kind="agent", key="one", name="다음 이름", expected_version=1), actor)
    assert store.rows["agent_profile", p["id"]].metadata["custom"] == "keep"
    saved = svc.save(MemorySave(title="이전", text="이전 사실", idempotency_key="one"), actor)
    store.rows["memory", saved["memory_id"]].status = "invalid"
    assert svc.query(MemoryQuery(), actor)["items"] == []
    assert len(svc.query(MemoryQuery(include_invalid=True), actor)["items"]) == 1
    assert store.rows["memory", saved["memory_id"]].user_id == owner_id(actor)


@pytest.mark.parametrize(
    "command",
    [
        {"kind": "agent", "key": "x", "name": " "},
        {"kind": "thread", "key": "x", "name": "x", "user_id": "forged"},
    ],
)
def test_contract_rejects_blank_and_owner_override(command):
    with pytest.raises(ValueError):
        ProfileSave(**command)
