import math

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_mock_engine
from sqlalchemy.exc import IntegrityError

from knowledge_app.app import create_app
from knowledge_app.embedding import Piece, SentenceEmbedder, validate_vectors
from knowledge_app.extraction import ExtractionError, extract, fetch_url
from knowledge_app.models import Base, Item, Revision
from knowledge_app.settings import Settings
from python_foundation.errors import AuthenticationRequired
from python_foundation.security import Actor


class TestVerifier:
    __test__ = False

    def verify(self, token):
        if token not in {"alice", "bob"}:
            raise AuthenticationRequired()
        return Actor("test", token, frozenset())


class TestEmbedder:
    __test__ = False
    profile_id = "test-profile"
    dimensions = 1024
    fail = False

    def split(self, text):
        return [Piece(text, 1, 0, len(text))]

    def encode(self, texts, *, query=False):
        if self.fail:
            raise RuntimeError("sensitive-provider-token")
        vectors = []
        for text in texts:
            vector = [0.0] * 1024
            vector[0] = 1.0 if "Oracle" in text else 0.1
            vector[1] = 1.0 if "요리" in text else 0.1
            norm = math.sqrt(sum(v * v for v in vector))
            vectors.append([v / norm for v in vector])
        return vectors


@pytest.fixture
def knowledge(tmp_path):
    settings = Settings(_env_file=None, database_url="sqlite:///" + str(tmp_path / "knowledge.db"))
    embedder = TestEmbedder()
    app = create_app(settings, embedder=embedder, verifier=TestVerifier())
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer alice"
        yield client, app.state.service, embedder


def test_roundtrip_and_user_isolation(knowledge):
    client, service, _ = knowledge
    result = client.post(
        "/api/v1/knowledge",
        json={"title": "Oracle 연결", "text": "Oracle 접속 오류 해결 방법", "tags": ["Oracle"]},
    )
    assert result.status_code == 202
    ids = result.json()
    assert service.process_one()
    assert not service.process_one()
    assert client.get("/api/v1/jobs/" + ids["job_id"]).json()["status"] == "READY"
    found = client.post("/api/v1/knowledge/search", json={"query": "Oracle 오류"}).json()["items"]
    assert found[0]["knowledge_id"] == ids["knowledge_id"]
    assert found[0]["matches"][0]["text"] == "Oracle 접속 오류 해결 방법"
    assert client.get(found[0]["content_uri"]).json()["text"] == "Oracle 접속 오류 해결 방법"
    client.headers["Authorization"] = "Bearer bob"
    assert client.get("/api/v1/knowledge").json()["items"] == []
    assert client.post("/api/v1/knowledge/search", json={"query": "Oracle"}).json()["items"] == []
    assert client.get("/api/v1/knowledge/" + ids["knowledge_id"]).status_code == 404
    assert client.get(found[0]["content_uri"]).status_code == 404
    assert client.get("/api/v1/jobs/" + ids["job_id"]).status_code == 404
    assert client.post("/api/v1/jobs/" + ids["job_id"] + "/retry").status_code == 404
    client.headers.clear()
    assert client.get("/api/v1/knowledge").status_code == 401


def test_failure_retry_and_atomic_visibility(knowledge):
    client, service, embedder = knowledge
    ids = client.post("/api/v1/knowledge", json={"title": "test", "text": "Oracle text"}).json()
    embedder.fail = True
    assert service.process_one()
    job = client.get("/api/v1/jobs/" + ids["job_id"]).json()
    assert job["status"] == "FAILED"
    assert "sensitive" not in str(job)
    assert client.get("/api/v1/knowledge/" + ids["knowledge_id"]).json()["revision_id"] is None
    embedder.fail = False
    assert client.post("/api/v1/jobs/" + ids["job_id"] + "/retry").status_code == 202
    assert client.post("/api/v1/jobs/" + ids["job_id"] + "/retry").status_code == 409
    assert service.process_one()
    assert client.get("/api/v1/jobs/" + ids["job_id"]).json()["status"] == "READY"


def test_filters_and_profile_isolation(knowledge):
    client, service, embedder = knowledge
    for category in ["database", "cooking"]:
        client.post(
            "/api/v1/knowledge", json={"title": category, "text": "Oracle 요리", "category": category}
        )
        service.process_one()
    response = client.post(
        "/api/v1/knowledge/search", json={"query": "Oracle", "category": "database"}
    ).json()
    assert len(response["items"]) == 1
    assert response["items"][0]["category"] == "database"
    embedder.profile_id = "other-model"
    response = client.post("/api/v1/knowledge/search", json={"query": "Oracle"})
    assert response.status_code == 409
    assert "EMBEDDING_PROFILE_MISMATCH" in response.text
    client.headers["Authorization"] = "Bearer bob"
    assert client.post("/api/v1/knowledge/search", json={"query": "Oracle"}).json()["items"] == []


def test_upload_and_source_validation(knowledge):
    client, service, _ = knowledge
    response = client.post(
        "/api/v1/knowledge/files",
        data={"title": "메모"},
        files={"file": ("note.md", "Oracle 원문".encode(), "text/markdown")},
    )
    assert response.status_code == 202
    assert service.process_one()
    assert (
        client.post(
            "/api/v1/knowledge", json={"title": "x", "text": "x", "url": "https://example.com"}
        ).status_code
        == 400
    )
    assert (
        client.post("/api/v1/knowledge", json={"title": "x", "text": "x", "user_id": "bob"}).status_code
        == 400
    )
    assert client.post("/api/v1/knowledge/search", json={"query": "   "}).status_code == 400
    assert (
        client.post(
            "/api/v1/knowledge/files",
            data={"title": "bad"},
            files={"file": ("x.exe", b"x", "application/octet-stream")},
        ).status_code
        == 400
    )


def test_database_rejects_cross_owner_reference(knowledge):
    _, service, _ = knowledge
    with service.factory.begin() as session:
        item = Item(owner_id="alice", title="x", knowledge_type="NOTE")
        session.add(item)
        session.flush()
        item_id = item.id
    with pytest.raises(IntegrityError), service.factory.begin() as session:
        session.add(Revision(owner_id="bob", item_id=item_id, source_type="TEXT", mime_type="text/plain"))


def test_extraction_and_url_boundary(monkeypatch):
    assert extract(b"<p>Hello</p><script>secret()</script>", "text/html", 100) == "\nHello"
    with pytest.raises(ExtractionError):
        extract(b"  ", "text/plain", 100)
    with pytest.raises(ExtractionError):
        extract(b"long text", "text/plain", 2)
    with pytest.raises(ExtractionError, match="URL_NOT_ALLOWED"):
        fetch_url("http://localhost", {"localhost"}, 100)
    monkeypatch.setattr("socket.getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("127.0.0.1", 443))])
    with pytest.raises(ExtractionError, match="URL_NOT_PUBLIC"):
        fetch_url("https://allowed.test", {"allowed.test"}, 100)


def test_model_configuration_boundaries():
    with pytest.raises(ValueError):
        SentenceEmbedder(Settings(_env_file=None, embedding_revision="moving-tag"))
    with pytest.raises(ValidationError):
        Settings(_env_file=None, embedding_dimensions=384)
    with pytest.raises(ValueError):
        validate_vectors([[float("nan")]], 1, 1)


def test_oracle_schema_compiles():
    statements = []
    engine = create_mock_engine(
        "oracle+oracledb://", lambda sql, *a, **k: statements.append(str(sql.compile(dialect=engine.dialect)))
    )
    Base.metadata.create_all(engine)
    assert any("VECTOR(1024,FLOAT32" in sql for sql in statements)
    assert any("vk_item_active_fk" in sql for sql in statements)


def test_dimension_environment_parsing(monkeypatch):
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "1024")
    assert Settings(_env_file=None).embedding_dimensions == 1024
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "384")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_bad_model_never_cached(monkeypatch):
    import sys
    from types import SimpleNamespace

    candidate = SimpleNamespace(get_sentence_embedding_dimension=lambda: 1024, max_seq_length=64)
    monkeypatch.setitem(
        sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=lambda *a, **k: candidate)
    )
    embedder = SentenceEmbedder(Settings(_env_file=None, embedding_revision="a" * 40))
    for _ in range(2):
        with pytest.raises(ValueError, match="capacity"):
            embedder.model()
        assert embedder._model is None


def test_memory_scopes_and_kinds(knowledge):
    client, service, _ = knowledge
    for scope, kind in [
        ("project:one", "DECISION"),
        ("project:two", "FACT"),
        ("global", "PREFERENCE"),
        ("thread:chat-1", "EPISODE"),
    ]:
        r = client.post(
            "/api/v1/knowledge", json=dict(title=scope, text="Oracle 기억", scope=scope, memory_kind=kind)
        )
        assert r.status_code == 202
        assert service.process_one()
    r = client.post(
        "/api/v1/knowledge/search",
        json=dict(query="Oracle", scopes=["PROJECT:one", "global"], memory_kinds=["DECISION"]),
    )
    assert [i["scope"] for i in r.json()["items"]] == ["project:one"]
    assert (
        len(
            client.get("/api/v1/knowledge", params=dict(scope="project:two", memory_kind="FACT")).json()[
                "items"
            ]
        )
        == 1
    )
    assert (
        client.post(
            "/api/v1/knowledge/search", json=dict(query="Oracle", scopes=["project:../private"])
        ).status_code
        == 400
    )
    assert client.get("/api/v1/knowledge", params=dict(scope="bad")).status_code == 400


def test_idempotent_save_is_owner_scoped(knowledge):
    client, service, _ = knowledge
    body = dict(title="Oracle", text="Oracle 기억", idempotency_key="request-one")
    first = client.post("/api/v1/knowledge", json=body).json()
    assert client.post("/api/v1/knowledge", json=body).json() == first
    assert service.process_one()
    repeated = client.post("/api/v1/knowledge", json=body).json()
    assert repeated["status"] == "READY" and repeated["knowledge_id"] == first["knowledge_id"]
    assert client.post("/api/v1/knowledge", json={**body, "text": "changed"}).status_code == 409
    assert len(client.get("/api/v1/knowledge").json()["items"]) == 1
    client.headers["Authorization"] = "Bearer bob"
    other = client.post("/api/v1/knowledge", json=body).json()
    assert other["knowledge_id"] != first["knowledge_id"]


def test_revision_history_failure_and_late_completion(knowledge):
    from knowledge_app.models import Job

    client, service, embedder = knowledge
    first = client.post("/api/v1/knowledge", json=dict(title="Oracle", text="Oracle version1")).json()
    assert service.process_one()
    path = "/api/v1/knowledge/" + first["knowledge_id"]
    second = client.post(
        path + "/revisions",
        json=dict(text="Oracle version2", expected_revision_id=first["revision_id"], change_note="수정"),
    ).json()
    assert client.get(path).json()["revision_id"] == first["revision_id"]
    assert (
        client.post(
            path + "/revisions", json=dict(text="stale", expected_revision_id=first["revision_id"])
        ).status_code
        == 409
    )
    embedder.fail = True
    assert service.process_one()
    embedder.fail = False
    assert client.get(path).json()["revision_id"] == first["revision_id"]
    third = client.post(
        path + "/revisions", json=dict(text="Oracle version3", expected_revision_id=second["revision_id"])
    ).json()
    assert service.process_one()
    assert client.post("/api/v1/jobs/" + second["job_id"] + "/retry").status_code == 202
    assert service.process_one()
    assert client.get(path).json()["revision_id"] == third["revision_id"]
    history = client.get(path + "/history").json()
    assert [r["revision_no"] for r in history["revisions"]] == [1, 2, 3]
    assert [e["event_type"] for e in history["events"] if e["event_type"] != "SOURCE_ACTIVATED"] == [
        "CREATED",
        "REVISED",
        "REVISED",
    ]
    assert (
        client.get(path + "/revisions/" + first["revision_id"] + "/content").json()["text"]
        == "Oracle version1"
    )
    with service.factory() as session:
        assert session.get(Job, second["job_id"]).status == "READY"


def test_retire_restore_and_authorization(knowledge):
    client, service, _ = knowledge
    first = client.post("/api/v1/knowledge", json=dict(title="Oracle", text="Oracle original")).json()
    other = client.post("/api/v1/knowledge", json=dict(title="Oracle2", text="Oracle replacement")).json()
    service.process_one()
    service.process_one()
    path = "/api/v1/knowledge/" + first["knowledge_id"]
    client.headers["Authorization"] = "Bearer bob"
    assert (
        client.post(
            path + "/revisions", json=dict(text="bad", expected_revision_id=first["revision_id"])
        ).status_code
        == 404
    )
    assert client.post(path + "/retire", json=dict(reason="bad")).status_code == 404
    assert client.post(path + "/restore", json={}).status_code == 404
    assert client.get(path + "/history").status_code == 404
    bob = client.post("/api/v1/knowledge", json=dict(title="bob", text="Oracle")).json()
    client.headers["Authorization"] = "Bearer alice"
    assert (
        client.post(path + "/retire", json=dict(reason="bad", superseded_by=bob["knowledge_id"])).status_code
        == 404
    )
    result = client.post(
        path + "/retire", json=dict(reason="이전 결정 폐기", superseded_by=other["knowledge_id"])
    )
    assert result.json()["lifecycle_status"] == "RETIRED"
    assert result.json()["superseded_by"] == other["knowledge_id"]
    assert len(client.post("/api/v1/knowledge/search", json=dict(query="Oracle")).json()["items"]) == 1
    assert (
        len(
            client.post("/api/v1/knowledge/search", json=dict(query="Oracle", include_retired=True)).json()[
                "items"
            ]
        )
        == 2
    )
    assert (
        client.post(
            path + "/revisions", json=dict(text="bad", expected_revision_id=first["revision_id"])
        ).status_code
        == 409
    )
    assert client.post(path + "/retire", json=dict(reason="again")).status_code == 409
    assert client.post(path + "/restore", json=dict(reason="복원")).json()["lifecycle_status"] == "ACTIVE"
    assert [
        e["event_type"]
        for e in client.get(path + "/history").json()["events"]
        if e["event_type"] != "SOURCE_ACTIVATED"
    ] == [
        "CREATED",
        "RETIRED",
        "RESTORED",
    ]


def test_worker_does_not_restore_retired_item(knowledge):
    client, service, _ = knowledge
    saved = client.post("/api/v1/knowledge", json=dict(title="Oracle", text="Oracle queued")).json()
    path = "/api/v1/knowledge/" + saved["knowledge_id"]
    assert client.post(path + "/retire", json=dict(reason="obsolete")).status_code == 200
    assert service.process_one()
    assert client.get(path).json()["lifecycle_status"] == "RETIRED"
    assert client.post("/api/v1/knowledge/search", json=dict(query="Oracle")).json()["items"] == []


def test_relevance_abstention_and_context_budget(knowledge):
    client, service, _ = knowledge
    client.post("/api/v1/knowledge", json=dict(title="조리법", text="요리 만드는 방법"))
    service.process_one()
    result = client.post("/api/v1/knowledge/search", json=dict(query="Oracle 접속")).json()
    assert result["items"] == [] and result["excluded_count"] == 1
    saved = client.post(
        "/api/v1/knowledge", json=dict(title="Oracle", text="Oracle DB 설정 " * 300, scope="project:one")
    ).json()
    service.process_one()
    card = client.post(
        "/api/v1/knowledge/context", json=dict(query="Oracle", scopes=["project:one"], max_chars=500)
    ).json()
    assert card["used_chars"] == 500 and card["generated_summary"] is False
    assert card["entries"][0]["revision_id"] == saved["revision_id"]
    assert card["entries"][0]["truncated"]
    client.headers["Authorization"] = "Bearer bob"
    assert client.post("/api/v1/knowledge/context", json=dict(query="Oracle")).json()["entries"] == []


def test_keyword_exact_match_survives_similarity_filter(knowledge):
    client, service, _ = knowledge
    client.post("/api/v1/knowledge", json=dict(title="Oracle 오류", text="요리"))
    service.process_one()
    found = client.post(
        "/api/v1/knowledge/search", json=dict(query="Oracle 오류", min_similarity=0.99)
    ).json()["items"]
    assert len(found) == 1 and found[0]["keyword_coverage"] == 1.0
    assert found[0]["similarity"] < 0.99


def sample_pptx():
    import io
    import zipfile

    content = io.BytesIO()
    pns = "http://schemas.openxmlformats.org/presentationml/2006/main"
    ans = "http://schemas.openxmlformats.org/drawingml/2006/main"
    rns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    with zipfile.ZipFile(content, "w") as archive:
        archive.writestr(
            "ppt/presentation.xml",
            f'<p:presentation xmlns:p="{pns}" xmlns:r="{rns}"><p:sldIdLst><p:sldId r:id="r2"/><p:sldId r:id="r1"/></p:sldIdLst></p:presentation>',
        )
        archive.writestr(
            "ppt/_rels/presentation.xml.rels",
            f'<Relationships><Relationship Id="r1" Target="slides/slide1.xml" Type="{rns}/slide"/><Relationship Id="r2" Target="slides/slide2.xml" Type="{rns}/slide"/></Relationships>',
        )
        for i in (1, 2):
            archive.writestr(
                f"ppt/slides/slide{i}.xml",
                f'<p:sld xmlns:p="{pns}" xmlns:a="{ans}"><a:p><a:r><a:t>Oracle 본문 {i}</a:t></a:r></a:p></p:sld>',
            )
        archive.writestr(
            "ppt/slides/_rels/slide2.xml.rels",
            f'<Relationships><Relationship Id="n1" Target="../notesSlides/notesSlide9.xml" Type="{rns}/notesSlide"/></Relationships>',
        )
        archive.writestr(
            "ppt/notesSlides/notesSlide9.xml",
            f'<p:notes xmlns:p="{pns}" xmlns:a="{ans}"><p:sp><p:nvSpPr><p:nvPr><p:ph type="body"/></p:nvPr></p:nvSpPr><a:p><a:t>발표 설명</a:t></a:p></p:sp><p:sp><p:ph type="sldNum"/><a:p><a:t>99</a:t></a:p></p:sp></p:notes>',
        )
    return content.getvalue()


def test_pptx_order_notes_upload_and_chunk_locations(knowledge):
    from types import SimpleNamespace

    from knowledge_app.extraction import NOTES_MARKER, PPTX_MIME

    data = sample_pptx()
    text = extract(data, PPTX_MIME, 1000)
    assert text == "Oracle 본문 2" + NOTES_MARKER + "발표 설명\fOracle 본문 1"
    embedder = SentenceEmbedder(Settings(_env_file=None, embedding_revision="a" * 40))
    embedder._model = SimpleNamespace(
        tokenizer=lambda text, **k: {"offset_mapping": [(i, i + 1) for i in range(len(text))]}
    )
    parts = embedder.split(text)
    assert [(p.page, p.source_part) for p in parts] == [(1, "body"), (1, "notes"), (2, "body")]
    assert all(text[p.start : p.end] == p.text for p in parts)
    with pytest.raises(ExtractionError, match="TEXT_TOO_LARGE"):
        extract(data, PPTX_MIME, 3)
    with pytest.raises(ExtractionError, match="PPTX_INVALID"):
        extract(b"not a zip", PPTX_MIME, 1000)
    client, service, _ = knowledge
    r = client.post(
        "/api/v1/knowledge/files",
        data=dict(title="슬라이드", scope="project:slides", memory_kind="DOCUMENT"),
        files={"file": ("sample.pptx", data, PPTX_MIME)},
    )
    assert r.status_code == 202
    assert service.process_one()
    ids = r.json()
    source = client.get(f"/api/v1/knowledge/{ids['knowledge_id']}/revisions/{ids['revision_id']}/content")
    assert source.json()["text"] == text


def test_pptx_ignores_large_unreferenced_media():
    import io
    import zipfile

    from knowledge_app.extraction import PPTX_MIME

    buffer = io.BytesIO(sample_pptx())
    with zipfile.ZipFile(buffer, "a", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("ppt/media/large.gif", b"x" * 10_000_001)
    assert "발표 설명" in extract(buffer.getvalue(), PPTX_MIME, 1000)


class FakeReranker:
    def __init__(self):
        self.passages = []
        self.bad = False

    def score(self, query, passages):
        self.passages.extend(passages)
        if self.bad:
            return [float("nan")] * len(passages)
        return [0.95 if "요리" in p else 0.1 for p in passages]


def test_reranker_recovers_below_cosine_gate_and_then_limits(knowledge):
    client, service, _ = knowledge
    wanted = client.post("/api/v1/knowledge", json={"title": "조리법", "text": "요리 비법"}).json()
    assert service.process_one()
    client.post("/api/v1/knowledge", json={"title": "Oracle", "text": "Oracle 연결"})
    assert service.process_one()
    baseline = client.post("/api/v1/knowledge/search", json={"query": "Oracle", "top_k": 1}).json()
    assert wanted["knowledge_id"] not in [i["knowledge_id"] for i in baseline["items"]]
    fake = FakeReranker()
    service.reranker = fake
    result = client.post("/api/v1/knowledge/search", json={"query": "Oracle", "top_k": 1}).json()
    assert result["items"][0]["knowledge_id"] == wanted["knowledge_id"]
    assert result["items"][0]["similarity"] < 0.28
    assert result["score_type"] == "reranker_sigmoid"
    assert result["reranker"]["pair_count"] == 2
    assert len(fake.passages) == 2
    strict = client.post("/api/v1/knowledge/search", json={"query": "Oracle", "min_similarity": 0.9}).json()
    assert strict["items"] == []
    fake.bad = True
    error = client.post("/api/v1/knowledge/search", json={"query": "Oracle"})
    assert error.status_code == 503
    assert "RERANKER_UNAVAILABLE" in error.text


def test_reranker_never_sees_wrong_owner_scope_retired_or_old_revision(knowledge):
    client, service, _ = knowledge
    fake = FakeReranker()
    service.reranker = fake
    for scope in ["project:one", "project:two"]:
        saved = client.post("/api/v1/knowledge", json={"title": "요리", "text": scope, "scope": scope}).json()
        assert service.process_one()
        if scope == "project:one":
            first = saved
    path = "/api/v1/knowledge/" + first["knowledge_id"]
    client.post(
        path + "/revisions", json={"text": "요리 current", "expected_revision_id": first["revision_id"]}
    )
    assert service.process_one()
    found = client.post("/api/v1/knowledge/search", json={"query": "요리", "scopes": ["project:one"]}).json()
    assert len(found["items"]) == 1
    assert fake.passages == ["요리\n요리 current"]
    fake.passages.clear()
    client.post(path + "/retire", json={"reason": "obsolete"})
    assert (
        client.post("/api/v1/knowledge/search", json={"query": "요리", "scopes": ["project:one"]}).json()[
            "items"
        ]
        == []
    )
    assert fake.passages == []
    client.headers["Authorization"] = "Bearer bob"
    assert client.post("/api/v1/knowledge/search", json={"query": "요리"}).json()["items"] == []
    assert fake.passages == []


def test_search_ui_is_public_but_knowledge_remains_authenticated(knowledge):
    client, _, _ = knowledge
    client.headers.clear()
    page = client.get("/knowledge")
    assert page.status_code == 200
    assert "지식 노트" in page.text
    assert page.headers["cache-control"] == "no-store"
    assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
    assert client.get("/").url.path == "/knowledge"
    assert client.get("/knowledge-assets/app.js").status_code == 200
    assert client.get("/knowledge-assets/style.css").status_code == 200
    assert client.get("/knowledge-assets/common.css").status_code == 200
    assert client.get("/knowledge-assets/.env").status_code == 404
    assert client.get("/api/v1/knowledge").status_code == 401
    assert client.post("/api/v1/knowledge/search", json={"query": "Oracle"}).status_code == 401


def test_machine_sources_accumulate_without_changing_old_revision(knowledge):
    client, service, _ = knowledge
    source_a = {
        "kind": "local_file",
        "location": "/work/docs/spec.md",
        "machine_id": "mac-a",
        "version": "commit-a",
        "locator": "lines 10-20",
    }
    first = client.post(
        "/api/v1/knowledge",
        json={"title": "설계", "text": "Oracle 설계", "origin_machine_id": "mac-a", "sources": [source_a]},
    ).json()
    assert service.process_one()
    path = "/api/v1/knowledge/" + first["knowledge_id"]
    source_b = {
        "kind": "git",
        "location": "https://example.com/repo",
        "version": "commit-b",
        "locator": "docs/spec.md",
    }
    second = client.post(
        path + "/revisions",
        json={
            "expected_revision_id": first["revision_id"],
            "text": "Oracle 보충",
            "origin_machine_id": "vm-b",
            "sources": [source_a, source_b],
        },
    ).json()
    assert service.process_one()
    content = client.get(path + "/revisions/" + second["revision_id"] + "/content").json()
    assert content["origin_machine_id"] == "vm-b"
    assert len(content["sources"]) == 2
    assert content["sources"][0]["machine_id"] == "mac-a"
    old = client.get(path + "/revisions/" + first["revision_id"] + "/content").json()
    assert old["origin_machine_id"] == "mac-a" and len(old["sources"]) == 1
    history = client.get(path + "/history").json()
    assert history["revisions"][1]["origin_machine_id"] == "vm-b"
    client.headers["Authorization"] = "Bearer bob"
    assert client.get(path + "/history").status_code == 404
    assert client.get(path + "/revisions/" + second["revision_id"] + "/content").status_code == 404


@pytest.mark.parametrize(
    "source",
    [
        {"kind": "local_file", "location": "/tmp/spec.md"},
        {"kind": "url", "location": "https://user:password@example.com/spec"},
        {"kind": "url", "location": "https://example.com/spec?token=secret"},
    ],
)
def test_invalid_source_rejected(knowledge, source):
    client, _, _ = knowledge
    assert (
        client.post(
            "/api/v1/knowledge", json={"title": "test", "text": "text", "sources": [source]}
        ).status_code
        == 400
    )


def test_file_upload_provenance(knowledge):
    import json

    client, service, _ = knowledge
    response = client.post(
        "/api/v1/knowledge/files",
        data={
            "title": "파일",
            "provenance": json.dumps(
                {
                    "origin_machine_id": "pc-a",
                    "sources": [{"kind": "local_file", "location": "C:/docs/file.txt", "machine_id": "pc-a"}],
                }
            ),
        },
        files={"file": ("file.txt", b"Oracle guide", "text/plain")},
    )
    assert response.status_code == 202
    assert service.process_one()
    ids = response.json()
    content = client.get(
        f"/api/v1/knowledge/{ids['knowledge_id']}/revisions/{ids['revision_id']}/content"
    ).json()
    assert content["origin_machine_id"] == "pc-a"
    assert content["sources"][0]["location"] == "C:/docs/file.txt"


def test_local_ui_auto_connect_requires_same_origin_and_loopback(tmp_path):
    token = "test-only-local-ui-token-long-enough"
    settings = Settings(
        _env_file=None, database_url="sqlite:///" + str(tmp_path / "ui.db"), dev_api_token=token
    )
    app = create_app(settings, embedder=TestEmbedder())
    headers = {"Origin": "http://127.0.0.1:8000", "Sec-Fetch-Site": "same-origin", "X-Knowledge-UI": "1"}
    with TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 123)) as client:
        response = client.post("/knowledge/local-connection", headers=headers)
        assert response.status_code == 200
        assert response.json()["token"] == token
        assert response.headers["cache-control"] == "no-store"
        assert client.get("/api/v1/knowledge").status_code == 401
        assert client.post("/knowledge/local-connection").status_code == 404
        for key, value in [
            ("Origin", "https://evil.invalid"),
            ("Sec-Fetch-Site", "cross-site"),
            ("Host", "evil.invalid"),
            ("X-Knowledge-UI", ""),
        ]:
            assert (
                client.post("/knowledge/local-connection", headers=headers | {key: value}).status_code == 404
            )
        settings.ui_auto_connect = False
        assert client.post("/knowledge/local-connection", headers=headers).status_code == 404
        settings.ui_auto_connect = True
        settings.api_host = "0.0.0.0"
        assert client.post("/knowledge/local-connection", headers=headers).status_code == 404
        settings.api_host = "127.0.0.1"
        settings.environment = "production"
        assert client.post("/knowledge/local-connection", headers=headers).status_code == 404
        settings.environment = "development"
    with TestClient(app, base_url="http://127.0.0.1:8000", client=("192.0.2.1", 123)) as client:
        assert client.post("/knowledge/local-connection", headers=headers).status_code == 404


def test_categories_are_owner_scoped_and_exclude_retired(knowledge):
    client, _, _ = knowledge
    item = client.post("/api/v1/knowledge", json={"title": "노트", "text": "내용", "category": "업무"}).json()
    assert client.get("/api/v1/knowledge/categories").json() == {"categories": ["업무"]}
    client.headers["Authorization"] = "Bearer bob"
    assert client.get("/api/v1/knowledge/categories").json() == {"categories": []}
    client.headers["Authorization"] = "Bearer alice"
    client.post("/api/v1/knowledge/" + item["knowledge_id"] + "/retire", json={"reason": "정리"})
    assert client.get("/api/v1/knowledge/categories").json() == {"categories": []}


def test_human_edit_preserves_original_and_rejects_stale_revision(knowledge):
    client, service, _ = knowledge
    first = client.post("/api/v1/knowledge", json={"title": "노트", "text": "원래 내용"}).json()
    assert service.process_one()
    base = "/api/v1/knowledge/" + first["knowledge_id"]
    command = {
        "text": "사람이 보충한 내용",
        "expected_revision_id": first["revision_id"],
        "edit_origin": "HUMAN",
        "change_note": "웹 화면 사용자 편집",
    }
    result = client.post(base + "/revisions", json=command)
    assert result.status_code == 202
    second = result.json()
    assert client.post(base + "/revisions", json=command).status_code == 409
    assert client.get(base).json()["revision_id"] == first["revision_id"]
    assert service.process_one()
    assert client.get(base).json()["revision_id"] == second["revision_id"]
    old = client.get(base + "/revisions/" + first["revision_id"] + "/content").json()
    new = client.get(base + "/revisions/" + second["revision_id"] + "/content").json()
    assert old["text"] == "원래 내용" and old["edit_origin"] == "API"
    assert new["text"] == command["text"] and new["edit_origin"] == "HUMAN"
    assert client.get(base + "/history").json()["revisions"][-1]["edit_origin"] == "HUMAN"
