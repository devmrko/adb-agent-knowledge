import asyncio
import json
from uuid import uuid4

import httpx
import pytest
from mcp.server.fastmcp.exceptions import ToolError

from knowledge_app.mcp_server import KnowledgeAPI, create_server
from knowledge_app.routing import MemoryRouter


@pytest.fixture(autouse=True)
def no_live_kev(monkeypatch):
    async def decide(self, request):
        return {"action": request.operation if request.explicit_request else "skip", "reason": "test"}

    monkeypatch.setattr(MemoryRouter, "decide", decide)


def test_tool_contracts_and_save_auth():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(202, json={"status": "QUEUED", "job_id": str(uuid4())})

    server = create_server(
        KnowledgeAPI("http://127.0.0.1:8000", "private-token", transport=httpx.MockTransport(handler))
    )
    tools = asyncio.run(server.list_tools())
    assert {t.name for t in tools} == {
        "knowledge_decide",
        "knowledge_recall",
        "knowledge_changes",
        "knowledge_change_get",
        "knowledge_change_reviews",
        "knowledge_change_resolve",
        "knowledge_change_retry",
        "knowledge_graph_extraction_schema",
        "knowledge_graph_proposals",
        "knowledge_graph_extraction_runs",
        "knowledge_graph_extract",
        "knowledge_graph_proposal_review",
        "knowledge_prepare_save",
        "knowledge_index_list",
        "knowledge_index_get",
        "knowledge_index_create",
        "knowledge_index_update",
        "knowledge_index_link",
        "knowledge_index_entries",
        "knowledge_index_history",
        "knowledge_get_summary",
        "knowledge_references",
        "knowledge_set_workflow",
        "knowledge_get_workflow",
        "knowledge_graph_entities",
        "knowledge_graph_entity",
        "knowledge_graph_assert",
        "knowledge_graph_revise",
        "knowledge_graph_history",
        "knowledge_graph_search",
        "knowledge_client_info",
        "knowledge_save",
        "knowledge_save_url",
        "knowledge_search",
        "knowledge_list",
        "knowledge_get_content",
        "knowledge_job_status",
        "knowledge_revise",
        "knowledge_retire",
        "knowledge_restore",
        "knowledge_history",
        "knowledge_context",
    }
    assert next(t for t in tools if t.name == "knowledge_search").annotations.readOnlyHint
    assert not next(t for t in tools if t.name == "knowledge_save").annotations.readOnlyHint
    result = asyncio.run(server.call_tool("knowledge_save", {"title": "제목", "text": "원문"}))
    assert "QUEUED" in str(result)
    assert "private-token" not in str(result)
    assert requests[0].headers["Authorization"] == "Bearer private-token"
    assert json.loads(requests[0].content)["text"] == "원문"


def test_content_paging_and_uuid_boundary():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"text": "abcdefghij"})

    server = create_server(
        KnowledgeAPI("http://localhost:8000", "token", transport=httpx.MockTransport(handler))
    )
    args = {"knowledge_id": str(uuid4()), "revision_id": str(uuid4()), "offset": 2, "max_chars": 3}
    result = asyncio.run(server.call_tool("knowledge_get_content", args))
    assert "cde" in str(result)
    assert "next_offset" in str(result)
    assert len(requests) == 1
    args["knowledge_id"] = "../../secrets"
    with pytest.raises(ToolError):
        asyncio.run(server.call_tool("knowledge_get_content", args))
    assert len(requests) == 1


def test_provider_errors_are_redacted():
    api = KnowledgeAPI(
        "http://localhost:8000",
        "secret",
        transport=httpx.MockTransport(lambda r: httpx.Response(500, text="password=secret; SQL statement")),
    )
    with pytest.raises(ToolError) as error:
        asyncio.run(api.request("GET", "/api/v1/knowledge"))
    assert "secret" not in str(error.value)
    assert "SQL statement" not in str(error.value)


def test_no_plaintext_remote_or_credentials_in_url():
    for url in ["http://example.com", "https://user:pass@example.com", "https://example.com/?token=x"]:
        with pytest.raises(ValueError):
            KnowledgeAPI(url, "token")


def test_read_tool_input_validation_prevents_http():
    def unexpected(request):
        raise AssertionError("No request should be issued")

    server = create_server(
        KnowledgeAPI("http://localhost:8000", "token", transport=httpx.MockTransport(unexpected))
    )
    with pytest.raises(ToolError):
        asyncio.run(server.call_tool("knowledge_search", {"query": "test", "top_k": 1000}))


def test_lifecycle_and_scoped_context_tool_paths():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"items": [], "status": "QUEUED"})

    server = create_server(
        KnowledgeAPI("http://localhost:8000", "token", transport=httpx.MockTransport(handler))
    )
    item, revision = str(uuid4()), str(uuid4())
    asyncio.run(
        server.call_tool(
            "knowledge_revise", dict(knowledge_id=item, expected_revision_id=revision, text="정정")
        )
    )
    assert requests[-1].url.path == f"/api/v1/knowledge/{item}/revisions"
    assert json.loads(requests[-1].content)["expected_revision_id"] == revision
    asyncio.run(
        server.call_tool(
            "knowledge_search", dict(query="결정", scopes=["project:one"], memory_kinds=["DECISION"])
        )
    )
    assert json.loads(requests[-1].content)["scopes"] == ["project:one"]
    asyncio.run(server.call_tool("knowledge_context", dict(query="결정", max_chars=500)))
    assert requests[-1].url.path.endswith("/context")
    asyncio.run(server.call_tool("knowledge_history", dict(knowledge_id=item)))
    assert requests[-1].url.path.endswith("/history")
    for name in ["knowledge_revise", "knowledge_retire", "knowledge_restore"]:
        tool = next(t for t in asyncio.run(server.list_tools()) if t.name == name)
        assert tool.annotations.readOnlyHint is False


def test_mcp_uses_client_machine_not_api_server(monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_MACHINE_ID", "laptop-a")
    monkeypatch.setenv("KNOWLEDGE_MACHINE_LABEL", "Development laptop")
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(202, json={"status": "QUEUED"})

    server = create_server(
        KnowledgeAPI("http://localhost:8000", "token", transport=httpx.MockTransport(handler))
    )
    asyncio.run(
        server.call_tool(
            "knowledge_save",
            {
                "title": "Note",
                "text": "Fact",
                "sources": [
                    {"kind": "local_file", "location": "/project/docs/design.md", "machine_id": "laptop-a"}
                ],
            },
        )
    )
    assert requests[0]["origin_machine_id"] == "laptop-a"
    assert requests[0]["sources"][0]["machine_id"] == "laptop-a"
    result = asyncio.run(server.call_tool("knowledge_client_info", {}))
    assert "laptop-a" in str(result)
    assert "token" not in str(result)


@pytest.mark.parametrize("graph_status", [200, 503])
def test_search_expands_graph_without_losing_source_on_failure(graph_status):
    item, revision = str(uuid4()), str(uuid4())
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path == "/api/v1/knowledge/search":
            return httpx.Response(
                200,
                json={
                    "items": [{"knowledge_id": item, "revision_id": revision, "matches": [], "title": "절차"}]
                },
            )
        return httpx.Response(
            graph_status,
            json={
                "status": "READY",
                "nodes": [{"id": "a", "label": "접수"}, {"id": "b", "label": "검토"}],
                "edges": [{"source": "a", "target": "b", "relation": "next", "evidence": "접수 후 검토"}],
            },
        )

    server = create_server(
        KnowledgeAPI("http://localhost:8000", "token", transport=httpx.MockTransport(handler))
    )
    result = asyncio.run(
        server.call_tool(
            "knowledge_search", {"query": "절차", "scopes": ["project:test"], "graph_mode": "always"}
        )
    )
    assert len(requests) == 3
    assert requests[1].url.path == "/api/v1/graph/search"
    assert json.loads(requests[1].content)["seed_revisions"] == [
        {"knowledge_id": item, "revision_id": revision}
    ]
    assert json.loads(requests[1].content)["query"] == "절차"
    assert json.loads(requests[1].content)["include_entity_matches"]
    assert json.loads(requests[0].content)["scopes"] == ["project:test"]
    assert requests[2].url.path == f"/api/v1/knowledge/{item}/revisions/{revision}/workflow"
    assert "READY" in str(result) if graph_status == 200 else "UNAVAILABLE" in str(result)
    assert "절차" in str(result)
    requests.clear()
    asyncio.run(server.call_tool("knowledge_search", {"query": "절차", "graph_mode": "never"}))
    assert len(requests) == 1


def test_change_event_hex_identifiers_preserved():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"status": "DONE"})

    server = create_server(
        KnowledgeAPI("http://localhost:8000", "token", transport=httpx.MockTransport(handler))
    )
    event = uuid4().hex
    asyncio.run(server.call_tool("knowledge_change_get", {"event_id": event}))
    asyncio.run(server.call_tool("knowledge_change_retry", {"event_id": event}))
    assert requests[0].url.path == "/api/v1/changes/" + event
    assert requests[1].url.path == "/api/v1/changes/" + event + "/retry"


def test_historical_graph_does_not_seed_from_current_vector_results():
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path.endswith("knowledge/search"):
            return httpx.Response(
                200, json={"items": [{"knowledge_id": str(uuid4()), "revision_id": str(uuid4())}]}
            )
        return httpx.Response(200, json={"status": "READY", "edges": [], "nodes": []})

    server = create_server(
        KnowledgeAPI("http://localhost:8000", "token", transport=httpx.MockTransport(handler))
    )
    asyncio.run(server.call_tool("knowledge_search", {"query": "Oracle", "known_at": "2026-01-01T00:00:00Z"}))
    graph = json.loads(requests[1].content)
    assert graph["seed_revisions"] == [] and graph["query"] == "Oracle"
    assert len(requests) == 2
