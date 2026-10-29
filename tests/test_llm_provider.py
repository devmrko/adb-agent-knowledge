import json

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from knowledge_app.graph_auto_contracts import AutoGraphSettings
from knowledge_app.graph_auto_extractor import ModelExtractor
from knowledge_app.llm import CompletionError, CompletionRequest
from knowledge_app.llm_http import OpenAICompatibleProvider

PAYLOAD = {
    "entities": [
        {"key": "p", "label": "Project A", "kind": "project", "mention": "Project A"},
        {"key": "s", "label": "Service B", "kind": "service", "mention": "Service B"},
    ],
    "relations": [{"subject": "p", "predicate": "uses", "object": "s", "quote": "Project A uses Service B."}],
}


class InProcessProvider:
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.requests = []

    def complete(self, request: CompletionRequest) -> str:
        self.requests.append(request)
        output = next(self.outputs)
        if isinstance(output, Exception):
            raise output
        return output


def test_injected_provider_runs_extraction_and_review_without_http(monkeypatch):
    monkeypatch.setattr(httpx, "Client", lambda **kw: pytest.fail("unexpected HTTP"))
    provider = InProcessProvider(
        [
            json.dumps(PAYLOAD),
            json.dumps({"verdicts": [{"index": 0, "verdict": "supported"}]}),
        ]
    )
    extractor = ModelExtractor(AutoGraphSettings(_env_file=None, model="local-or-sdk"), provider)
    result = extractor.extract("Project A uses Service B.", [])
    assert len(result.relations) == 1
    assert len(provider.requests) == 2
    assert provider.requests[0].model == "local-or-sdk"
    assert "entities" in provider.requests[0].json_schema["properties"]
    assert "verdicts" in provider.requests[1].json_schema["properties"]
    assert json.loads(provider.requests[1].user)["extraction"]["relations"]


@pytest.mark.parametrize("output", [None, "", "x" * 1_000_001, RuntimeError("private provider credentials")])
def test_custom_provider_invalid_results_and_failures_are_safe(output):
    extractor = ModelExtractor(AutoGraphSettings(_env_file=None, model="test"), InProcessProvider([output]))
    with pytest.raises(CompletionError) as error:
        extractor.complete("system", {})
    assert "private" not in str(error.value)
    assert str(error.value) in {"invalid_response", "provider_failed"}


def request():
    return CompletionRequest(
        model="test-model",
        system="system",
        user='{"source":"text"}',
        json_schema={"type": "object"},
        max_output_tokens=123,
        timeout_seconds=7,
    )


def mock_http(monkeypatch, handler):
    original = httpx.Client

    def factory(**kwargs):
        assert kwargs == {"timeout": 7, "trust_env": False, "follow_redirects": False}
        return original(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr("knowledge_app.llm_http.httpx.Client", factory)


def test_http_adapter_maps_request_and_keeps_openrouter_controls(monkeypatch):
    def handler(req):
        assert str(req.url) == "https://openrouter.ai/api/v1/chat/completions"
        assert req.headers["Authorization"] == "Bearer test-only"
        body = json.loads(req.content)
        assert body["model"] == "test-model" and body["max_tokens"] == 123
        assert body["messages"][1]["content"] == request().user
        assert body["response_format"]["json_schema"]["schema"] == {"type": "object"}
        assert body["provider"] == {"require_parameters": True, "data_collection": "deny"}
        assert body["reasoning"] == {"enabled": False}
        return httpx.Response(
            200, json={"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}]}
        )

    mock_http(monkeypatch, handler)
    provider = OpenAICompatibleProvider(
        url="https://openrouter.ai/api/v1",
        allow_remote=True,
        api_key=SecretStr("test-only"),
        structured_output=True,
    )
    assert provider.complete(request()) == "{}"


@pytest.mark.parametrize(
    "response,code",
    [
        (httpx.Response(401, text="private provider credentials"), "provider_failed"),
        (httpx.Response(200, content=b"x" * 1_000_001), "response_too_large"),
        (httpx.Response(200, json={"choices": []}), "provider_failed"),
        (httpx.Response(200, json={"choices": [{"finish_reason": "length"}]}), "incomplete_response"),
        (httpx.Response(200, json={"choices": [{"message": {"content": None}}]}), "invalid_response"),
        (httpx.Response(302, headers={"location": "https://other.invalid"}), "provider_failed"),
    ],
)
def test_http_provider_rejects_unsafe_or_incomplete_responses(monkeypatch, response, code):
    mock_http(monkeypatch, lambda _: response)
    provider = OpenAICompatibleProvider(url="http://127.0.0.1:11434/v1")
    with pytest.raises(CompletionError) as error:
        provider.complete(request())
    assert str(error.value) == code


def test_http_provider_remote_opt_in_and_known_factory_only():
    with pytest.raises(ValueError):
        OpenAICompatibleProvider(url="https://example.com/v1")
    with pytest.raises(ValidationError):
        AutoGraphSettings(_env_file=None, provider="oci_sdk")
