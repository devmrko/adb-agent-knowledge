import asyncio
import json

import httpx
import pytest
from pydantic import ValidationError

from knowledge_app.routing import MemoryDecision, MemoryRouter, RoutingSettings


@pytest.mark.parametrize(
    "operation,score,expected",
    [
        ("lookup", 0.19, "skip"),
        ("lookup", 0.2, "lookup"),
        ("save", 0.24, "skip"),
        ("save", 0.4, "agent_review"),
        ("save", 0.7, "save"),
    ],
)
def test_scores(operation, score, expected):
    requests = []

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        key = next(iter(body["questions"]))
        return httpx.Response(200, json={"answers": {key: {"type": "noul", "noul": score}}})

    router = MemoryRouter(RoutingSettings(_env_file=None), transport=httpx.MockTransport(handler))
    result = asyncio.run(
        router.decide(MemoryDecision(operation=operation, text="확인한 결정", verified=True))
    )
    assert result["action"] == expected and result["model_called"]
    assert len(requests) == 1


@pytest.mark.parametrize(
    "fields,action",
    [
        ({"operation": "lookup", "explicit_request": True}, "lookup"),
        ({"operation": "save", "explicit_request": True}, "save"),
        ({"operation": "save", "explicit_request": True, "storage_allowed": False}, "skip"),
        ({"operation": "save", "explicit_request": True, "contains_sensitive": True}, "skip"),
        ({"operation": "save"}, "skip"),
    ],
)
def test_policy_precedes_model(fields, action):
    def handler(request):
        raise AssertionError("Policy should avoid model call")

    router = MemoryRouter(RoutingSettings(_env_file=None), transport=httpx.MockTransport(handler))
    result = asyncio.run(router.decide(MemoryDecision(text="test", **fields)))
    assert result["action"] == action and not result["model_called"]


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(422, json={"detail": "private source"}),
        httpx.Response(200, json={"answers": {"need_lookup": {"type": "noul", "noul": True}}}),
        httpx.Response(200, json={"answers": {"need_lookup": {"type": "noul", "noul": 1.1}}}),
        httpx.Response(200, json={"truncated": True}),
        httpx.Response(200, json={}),
    ],
)
def test_invalid_response_falls_back_without_leaking(response):
    router = MemoryRouter(RoutingSettings(_env_file=None), transport=httpx.MockTransport(lambda r: response))
    result = asyncio.run(router.decide(MemoryDecision(operation="lookup", text="test")))
    assert result["action"] == "agent_review"
    assert "private source" not in str(result)


def test_timeout_and_local_url_boundary():
    def handler(request):
        raise httpx.ReadTimeout("private text")

    router = MemoryRouter(RoutingSettings(_env_file=None), transport=httpx.MockTransport(handler))
    assert (
        asyncio.run(router.decide(MemoryDecision(operation="save", text="test", verified=True)))["action"]
        == "agent_review"
    )
    for url in ["https://example.com", "http://127.0.0.1@evil.test", "http://localhost/?token=x"]:
        with pytest.raises(ValidationError):
            RoutingSettings(_env_file=None, url=url)


def test_context_resolution_uses_scores_not_phrase_rules():
    from knowledge_app.routing import MemoryDecision, MemoryRouter, RoutingSettings

    class Provider:
        def __init__(self, scores):
            self.scores = scores

        async def score(self, state, questions):
            assert set(questions) == {"need_lookup", "use_context", "standalone_query"}
            return self.scores

    for prompt in [
        "남은건?",
        "그 부분은 앞서 정한 방식으로 끝까지 처리해 주시겠어요?",
        "Please finish the remaining work.",
    ]:
        router = MemoryRouter(
            RoutingSettings(_env_file=None),
            provider=Provider({"need_lookup": 0.9, "use_context": 0.9, "standalone_query": 0.1}),
        )
        out = asyncio.run(
            router.decide(
                MemoryDecision(
                    operation="lookup", text=prompt, context="Oracle v3 설치 검증", resolve_context=True
                )
            )
        )
        assert out["action"] == "lookup" and out["context_used"]
        assert "Oracle v3" in out["retrieval_query"]
    router = MemoryRouter(
        RoutingSettings(_env_file=None),
        provider=Provider({"need_lookup": 0.9, "use_context": 0.1, "standalone_query": 0.9}),
    )
    out = asyncio.run(
        router.decide(
            MemoryDecision(
                operation="lookup",
                text="내 커피 추출 기록 찾아줘",
                context="Oracle v3 설치 검증",
                resolve_context=True,
            )
        )
    )
    assert out["retrieval_query"] == "내 커피 추출 기록 찾아줘"
    router = MemoryRouter(
        RoutingSettings(_env_file=None),
        provider=Provider({"need_lookup": 0.9, "use_context": 0.5, "standalone_query": 0.5}),
    )
    out = asyncio.run(router.decide(MemoryDecision(operation="lookup", text="그건?", resolve_context=True)))
    assert out["action"] == "agent_review" and out["retrieval_query"] is None
