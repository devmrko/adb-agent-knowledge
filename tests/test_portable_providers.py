import asyncio
import json

import httpx
import pytest
from pydantic import ValidationError

from knowledge_app.embedding import RemoteEmbedder, SentenceEmbedder, create_embedder
from knowledge_app.routing import MemoryDecision, MemoryRouter, RoutingSettings
from knowledge_app.settings import Settings


def remote_settings(**extra):
    return Settings(
        _env_file=None,
        embedding_provider="openai",
        embedding_url="https://models.example/v1",
        embedding_model="test",
        embedding_revision="fixed-v1",
        **extra,
    )


def test_remote_embedding_batch_order_prefix_and_normalization():
    calls = []

    def handle(request):
        body = json.loads(request.content)
        calls.append(body)
        assert request.headers["Authorization"] == "Bearer test-secret"
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": i, "embedding": [float(i + 1), 1.0] + [0.0] * 1022}
                    for i in reversed(range(len(body["input"])))
                ]
            },
        )

    settings = remote_settings(
        embedding_api_key="test-secret", embedding_batch_size=2, embedding_query_prefix="query: "
    )
    embedder = RemoteEmbedder(settings, transport=httpx.MockTransport(handle))
    result = embedder.encode(["가", "나", "다"], query=True)
    assert len(result) == 3
    assert calls[0]["input"] == ["query: 가", "query: 나"]
    assert result[0][0] == pytest.approx(2**-0.5)
    assert result[1][0] > result[0][0]
    assert len(calls) == 2


@pytest.mark.parametrize(
    "data",
    [
        [],
        [{"index": 0, "embedding": [0.0] * 1024}],
        [{"index": 1, "embedding": [1.0] * 1024}],
        [{"index": 0, "embedding": [True] * 1024}],
    ],
)
def test_remote_rejects_invalid_vectors(data):
    e = RemoteEmbedder(
        remote_settings(), transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"data": data}))
    )
    with pytest.raises(ValueError, match="Remote embedding failed"):
        e.encode(["text"])


def test_remote_errors_redacted_and_no_redirects():
    def handle(r):
        return httpx.Response(302, headers={"Location": "https://untrusted.example"}, text="SECRET")

    e = RemoteEmbedder(remote_settings(), transport=httpx.MockTransport(handle))
    with pytest.raises(ValueError) as error:
        e.encode(["text"])
    assert "SECRET" not in str(error.value)


def test_chunk_offsets_and_profile_separation():
    e = RemoteEmbedder(remote_settings(embedding_chunk_chars=64, embedding_overlap_chars=8))
    text = "한국어 " * 40 + "\f" + "둘째 페이지"
    pieces = e.split(text)
    assert all(text[p.start : p.end] == p.text for p in pieces)
    assert pieces[-1].page == 2
    other = RemoteEmbedder(remote_settings(embedding_query_prefix="query: "))
    assert e.profile_id != other.profile_id
    local = Settings(_env_file=None, embedding_revision="a" * 40)
    assert isinstance(create_embedder(local), SentenceEmbedder)


def test_remote_kev_requires_consent_and_https():
    with pytest.raises(ValidationError):
        RoutingSettings(_env_file=None, url="https://kev.example")
    with pytest.raises(ValidationError):
        RoutingSettings(_env_file=None, url="http://kev.example", allow_remote=True)
    settings = RoutingSettings(_env_file=None, url="https://kev.example", allow_remote=True, api_key="secret")

    def handle(request):
        assert request.headers["Authorization"] == "Bearer secret"
        return httpx.Response(200, json={"answers": {"need_lookup": {"type": "noul", "noul": 0.8}}})

    router = MemoryRouter(settings, transport=httpx.MockTransport(handle))
    assert (
        asyncio.run(router.decide(MemoryDecision(operation="lookup", text="이전 결정")))["action"] == "lookup"
    )


def test_decision_provider_injection_and_explicit_override():
    class Fake:
        async def score(self, state, questions):
            return {key: 0.0 for key in questions}

    router = MemoryRouter(RoutingSettings(_env_file=None), provider=Fake())
    assert asyncio.run(router.decide(MemoryDecision(operation="lookup", text="hello")))["action"] == "skip"
    assert (
        asyncio.run(router.decide(MemoryDecision(operation="lookup", text="find", explicit_request=True)))[
            "action"
        ]
        == "lookup"
    )
