import asyncio

import httpx
from fastapi.testclient import TestClient

from knowledge_app.mcp_server import KnowledgeAPI, create_server
from scripts.memory_prompt_hook import collect, render_context
from tests.test_browser_session import ORIGIN, login, make_app
from tests.test_knowledge import knowledge  # noqa: F401
from tests.test_memory_prompt_hook import Session


def command(version=0):
    return {
        "expected_version": version,
        "approved": True,
        "change_note": "사용자 승인",
        "rules": [
            {"id": "formal", "title": "존댓말", "instruction": "존댓말을 사용한다.", "scope": "global"},
            {"id": "project", "title": "프로젝트", "instruction": "간단히 접근한다.", "scope": "project:a"},
            {"id": "disabled", "title": "미사용", "instruction": "미사용 문구", "enabled": False},
        ],
    }


def test_principles_isolation_conflict_history_and_scopes(knowledge):  # noqa: F811
    c, _, _ = knowledge
    assert c.get("/api/v1/principles").json() == {"version": 0, "rules": []}
    assert c.put("/api/v1/principles", json=command()).json()["version"] == 1
    assert c.put("/api/v1/principles", json=command()).status_code == 409
    assert c.put("/api/v1/principles", json=command(99)).status_code == 409
    resolved = c.post("/api/v1/principles/resolve", json={"scopes": ["project:a"]}).json()
    assert [r["id"] for r in resolved["rules"]] == ["formal", "project"]
    assert len(c.post("/api/v1/principles/resolve", json={"scopes": ["project:b"]}).json()["rules"]) == 1
    update = command(1)
    update["rules"] = []
    assert c.put("/api/v1/principles", json=update).status_code == 200
    history = c.get("/api/v1/principles/history?limit=1").json()
    assert history["items"][0]["version"] == 2 and history["next_offset"] == 1
    assert len(c.get("/api/v1/principles/history?offset=1").json()["items"][0]["rules"]) == 3
    c.headers["Authorization"] = "Bearer bob"
    assert c.get("/api/v1/principles").json()["version"] == 0
    assert c.get("/api/v1/principles/history").json()["items"] == []
    assert c.put("/api/v1/principles", json=command(2)).status_code == 409
    assert c.put("/api/v1/principles", json=command()).status_code == 200


def test_principle_validation(knowledge):  # noqa: F811
    c, _, _ = knowledge
    for mutate in [
        lambda x: x.update(approved=False),
        lambda x: x["rules"].append(x["rules"][0]),
        lambda x: x["rules"][0].update(scope="thread:x"),
        lambda x: x["rules"][0].update(instruction=""),
        lambda x: x["rules"][0].update(instruction="x" * 601),
        lambda x: x.update(rules=[dict(id=str(i), title="a", instruction="x" * 600) for i in range(11)]),
    ]:
        body = command()
        mutate(body)
        assert c.put("/api/v1/principles", json=body).status_code == 400
    assert c.get("/api/v1/principles").json()["version"] == 0


def test_principles_cookie_csrf_and_mixed_auth(tmp_path):
    with TestClient(make_app(tmp_path), base_url=ORIGIN) as c:
        assert c.put("/api/v1/principles", json=command()).status_code == 401
        csrf = login(c).json()["csrf"]
        assert c.put("/api/v1/principles", json=command()).status_code == 403
        for origin, token in [("https://evil.test", csrf), (ORIGIN, "wrong")]:
            assert (
                c.put(
                    "/api/v1/principles", json=command(), headers={"Origin": origin, "X-CSRF-TOKEN": token}
                ).status_code
                == 403
            )
        assert (
            c.put(
                "/api/v1/principles", json=command(), headers={"Origin": ORIGIN, "X-CSRF-TOKEN": csrf}
            ).status_code
            == 200
        )
        assert c.get("/api/v1/principles", headers={"Authorization": "Bearer invalid"}).status_code == 401
        assert c.get("/api/v1/principles", headers={"Authorization": "Bearer bob"}).json()["version"] == 0
        assert (
            c.put("/api/v1/principles", json=command(), headers={"Authorization": "Bearer bob"}).status_code
            == 200
        )


def test_hook_always_includes_principles_and_separates_references():
    for prompt in ["안녕", "password=do-not-send"]:
        session = Session("skip")
        result, calls = asyncio.run(collect(session, {"prompt": prompt, "cwd": "/work"}, {}))
        assert calls == ["knowledge_decide"]
        assert session.calls[0][1]["principle_scopes"] == ["global"]
        assert result["user_principles"]["version"] == 2
        context = render_context(result, "check")
        assert context.index("존댓말") < context.index("untrusted retrieved")
        assert "do-not-send" not in context


def test_hook_missing_principles_fails_closed():
    import pytest

    class OldSession(Session):
        async def call_tool(self, name, args):
            result = await super().call_tool(name, args)
            result.structuredContent.pop("user_principles", None)
            return result

    with pytest.raises(RuntimeError, match="principles unavailable"):
        asyncio.run(collect(OldSession("skip"), {"prompt": "안녕", "cwd": "/work"}, {}))


def test_mcp_principles_do_not_go_to_kev_or_add_tools():
    calls = []

    class Router:
        async def decide(self, request):
            assert not hasattr(request, "principle_scopes")
            return {"action": "skip"}

    def handler(request):
        calls.append(request)
        assert request.url.path == "/api/v1/principles/resolve"
        assert b"scopes" in request.content and b"hello" not in request.content
        return httpx.Response(200, json={"status": "READY", "version": 3, "rules": []})

    async def run():
        server = create_server(
            KnowledgeAPI("http://127.0.0.1:8000", "test", transport=httpx.MockTransport(handler)),
            Router(),
            profile="memory",
        )
        assert len(await server.list_tools()) == 22
        result = await server.call_tool(
            "knowledge_decide", {"operation": "lookup", "text": "hello", "principle_scopes": ["global"]}
        )
        assert "user_principles" in str(result)
        await server.call_tool("knowledge_decide", {"operation": "lookup", "text": "hello"})

    asyncio.run(run())
    assert len(calls) == 1
