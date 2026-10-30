import pytest
from sqlalchemy import MetaData
from sqlalchemy.dialects import oracle
from sqlalchemy.schema import CreateTable
from test_knowledge import knowledge as knowledge_fixture  # noqa: F401
from test_shared_graph import entity, source

from knowledge_app.graph_ops_schema_v10 import tables


@pytest.fixture
def ops(knowledge_fixture):  # noqa: F811
    client, service, _ = knowledge_fixture
    service.settings.workflow_rdf_enabled = True
    evidence = source(
        client, service, "인증 서비스의 별칭은 auth 서버다. 저장소 식별자는 org/auth다.", "project:auth"
    )
    eid = entity(client, "auth-service", "project:auth", "인증 서비스")
    return client, service, evidence, eid


def bind(client, evidence, eid, **kwargs):
    body = dict(
        entity_id=eid,
        kind="alias",
        namespace="name",
        value="auth 서버",
        evidence=evidence,
        note="원문의 별칭 확인",
        expected_version=0,
    )
    body.update(kwargs)
    return client.post("/api/v1/graph/identities", json=body)


def resolve(client, query="auth 서버"):
    return client.post(
        "/api/v1/graph/identities/resolve", json={"query": query, "scopes": ["project:auth"]}
    ).json()


def test_binding_evidence_conflicts_history_and_isolation(ops):
    client, _, evidence, eid = ops
    row = bind(client, evidence, eid)
    assert row.status_code == 200, row.text
    row = row.json()
    assert resolve(client)["items"][0]["entity"]["id"] == eid
    assert not resolve(client)["ambiguous"]
    assert bind(client, evidence, eid).status_code == 409
    assert bind(client, {**evidence, "quote": "없는 인용"}, eid, expected_version=1).status_code == 400
    changed = bind(
        client, evidence, eid, expected_version=1, note="사용자가 별칭 연결 철회", status="RETRACTED"
    )
    assert changed.status_code == 200
    assert not any(c["exact"] for c in resolve(client)["items"])
    history = client.get("/api/v1/graph/operations/" + row["id"]).json()["items"]
    assert [r["version"] for r in history] == [2, 1]
    assert history[1]["snapshot"]["status"] == "ACTIVE"
    client.headers["Authorization"] = "Bearer bob"
    assert not any(c["exact"] for c in resolve(client)["items"])
    assert client.get("/api/v1/graph/operations/" + row["id"]).json()["items"] == []
    assert bind(client, evidence, eid).status_code == 404


def test_ambiguous_alias_and_unique_external_key(ops):
    client, _, evidence, eid = ops
    other = entity(client, "auth-staging", "project:auth", "스테이징 인증")
    assert bind(client, evidence, eid).status_code == 200
    assert bind(client, evidence, other).status_code == 200
    assert resolve(client)["ambiguous"]
    external = dict(kind="external", namespace="repository", value="org/auth")
    first = bind(client, evidence, eid, **external).json()
    assert bind(client, evidence, other, **external).status_code == 409
    correction = bind(
        client, evidence, other, expected_version=1, note="사용자가 실제 저장소 대상 정정", **external
    )
    assert correction.status_code == 200
    assert correction.json()["id"] == first["id"]
    assert resolve(client, "org/auth")["items"][0]["entity"]["id"] == other


def test_revision_invalidates_binding_and_creates_review(ops):
    client, service, evidence, eid = ops
    assert bind(client, evidence, eid).status_code == 200
    path = "/api/v1/graph/reviews/" + evidence["knowledge_id"]
    rows = client.get("/api/v1/graph/reviews").json()["items"]
    assert rows[0]["review"]["status"] == "PENDING"
    body = dict(
        revision_id=evidence["revision_id"],
        expected_version=0,
        status="REVIEWING",
        note="원문 전체 확인 시작",
    )
    assert client.post(path, json=body).status_code == 200
    assert client.post(path, json=body).status_code == 409
    done = client.post(
        path,
        json={
            **body,
            "expected_version": 1,
            "status": "COMPLETE",
            "outcome": "NONE",
            "note": "원문 전체 검토; 업무 관계 없음",
        },
    )
    assert done.status_code == 200, done.text
    assert client.get("/api/v1/graph/reviews").json()["items"] == []
    revised = client.post(
        "/api/v1/knowledge/" + evidence["knowledge_id"] + "/revisions",
        json={"expected_revision_id": evidence["revision_id"], "text": evidence["quote"] + " 추가 설명."},
    ).json()
    assert service.process_one()
    assert not any(c["exact"] for c in resolve(client)["items"])
    bindings = client.get(f"/api/v1/graph/entities/{eid}/identities").json()["items"]
    assert bindings[0]["version"] == 1 and not bindings[0]["evidence_current"]
    refreshed = bind(client, {**evidence, "revision_id": revised["revision_id"]}, eid, expected_version=1)
    assert refreshed.status_code == 200
    assert any(c["exact"] for c in resolve(client)["items"])
    backlog = client.get("/api/v1/graph/reviews").json()["items"]
    assert backlog[0]["revision_id"] == revised["revision_id"]
    assert backlog[0]["review"]["status"] == "PENDING"
    assert client.post(path, json={**body, "expected_version": 2}).status_code == 409
    assert bind(client, evidence, eid, expected_version=1).status_code == 409
    client.post("/api/v1/knowledge/" + evidence["knowledge_id"] + "/retire", json={"reason": "테스트 종료"})
    assert client.get("/api/v1/graph/reviews").json()["items"] == []
    assert client.get("/api/v1/graph/operations/" + done.json()["id"]).json()["items"]


def test_review_evidence_guard_and_reclaim(ops):
    client, _, evidence, eid = ops
    target = entity(client, "auth-db", "project:auth", "인증 저장소")
    relation = client.post(
        "/api/v1/graph/assertions",
        json=dict(
            scope="project:auth",
            subject_id=eid,
            object_id=target,
            predicate="uses",
            verified=True,
            evidence=[evidence],
        ),
    )
    assert relation.status_code == 200
    path = "/api/v1/graph/reviews/" + evidence["knowledge_id"]
    body = dict(
        revision_id=evidence["revision_id"],
        expected_version=0,
        status="COMPLETE",
        outcome="RELATIONS",
        note="검토 완료",
    )
    assert client.post(path, json=body).status_code == 409
    assert client.post(path, json={**body, "status": "REVIEWING", "outcome": None}).status_code == 200
    assert (
        client.post(
            path,
            json={
                **body,
                "status": "REVIEWING",
                "outcome": None,
                "expected_version": 1,
                "note": "중단된 작업 이어받음",
            },
        ).status_code
        == 200
    )
    assert client.post(path, json={**body, "expected_version": 2, "outcome": "NONE"}).status_code == 409
    assert client.post(path, json={**body, "expected_version": 2}).status_code == 200


def test_explore_cafesto_dependencies_and_evidence(ops):
    client, service, _, _ = ops
    ev = source(
        client,
        service,
        "Cafesto UX는 Cafesto의 일부다. Cafesto는 TypeScript Foundation에서 생성됐다.",
        "project:cafesto",
    )
    ux = entity(client, "cafesto:ux", "project:cafesto", "Cafesto UX")
    project = entity(client, "cafesto", "project:cafesto", "Cafesto")
    base = entity(client, "typescript-foundation", "global", "TypeScript Foundation")
    for a, p, b in [(ux, "part_of", project), (project, "created_from", base)]:
        assert (
            client.post(
                "/api/v1/graph/assertions",
                json=dict(
                    scope="project:cafesto",
                    subject_id=a,
                    predicate=p,
                    object_id=b,
                    verified=True,
                    evidence=[ev],
                ),
            ).status_code
            == 200
        )
    result = client.post(
        "/api/v1/graph/explore",
        json={
            "intent": "dependencies",
            "search": {"entity_ids": [base], "scopes": ["project:cafesto"], "depth": 2},
        },
    ).json()
    assert len(result["edges"]) == 2 and result["paths"]
    assert result["candidate_backend"] == "relational"
    assert result["storage"] == "sqlite_test"
    assert client.post(
        "/api/v1/graph/explore",
        json={
            "intent": "evidence",
            "search": {"entity_ids": [ux], "scopes": ["project:cafesto"], "depth": 2},
        },
    ).json()["edges"]


def test_oracle_schema_compiles():
    for table in tables(MetaData()).values():
        ddl = str(CreateTable(table).compile(dialect=oracle.dialect()))
        assert "CREATE TABLE" in ddl


def test_existing_source_backlog_and_source_owner_boundary(ops):
    from sqlalchemy import delete

    from knowledge_app.graph_ops_models import GraphReview

    client, service, evidence, eid = ops
    with service.factory.begin() as session:
        session.execute(delete(GraphReview))
    pending = client.get("/api/v1/graph/reviews?limit=1").json()["items"][0]
    assert pending["review"]["id"] is None and pending["review"]["version"] == 0
    client.headers["Authorization"] = "Bearer bob"
    assert client.get("/api/v1/graph/reviews").json()["items"] == []
    assert (
        client.post(
            "/api/v1/graph/reviews/" + evidence["knowledge_id"],
            json={
                "revision_id": evidence["revision_id"],
                "expected_version": 0,
                "status": "REVIEWING",
                "note": "attempt",
            },
        ).status_code
        == 404
    )


def test_documented_demo_is_repeatable(knowledge_fixture):  # noqa: F811
    import asyncio

    from scripts.demo_graph_relations import run

    client, service, _ = knowledge_fixture
    service.settings.workflow_rdf_enabled = True

    class API:
        async def request(self, method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            assert response.is_success, response.text
            if path == "/api/v1/knowledge":
                service.process_one()
            return response.json()

    first = asyncio.run(run(API()))
    second = asyncio.run(run(API()))
    assert first["knowledge_id"] == second["knowledge_id"]
    assert len(second["results"]["dependencies"]["edges"]) == 2
    assert len(second["results"]["evidence"]["edges"]) == 2


def test_identity_and_review_audit_actor_and_owner_isolation(ops):
    client, _, evidence, eid = ops
    row = bind(client, evidence, eid).json()
    review = client.post(
        "/api/v1/graph/reviews/" + evidence["knowledge_id"],
        json=dict(
            revision_id=evidence["revision_id"],
            expected_version=0,
            status="REVIEWING",
            note="Audit attribution test",
        ),
    )
    assert review.status_code == 200
    for table, identifier, operation in (
        ("vk_g_identity", row["id"], "GRAPH_IDENTITY_BIND"),
        ("vk_g_review", review.json()["id"], "GRAPH_REVIEW"),
    ):
        events = client.get("/api/v1/changes", params={"table": table, "target_id": identifier}).json()[
            "items"
        ]
        matched = [e for e in events if e["operation"] == operation]
        assert matched and all(e["actor_subject"] == "alice" for e in matched)
        client.headers["Authorization"] = "Bearer bob"
        assert (
            client.get("/api/v1/changes", params={"table": table, "target_id": identifier}).json()["items"]
            == []
        )
        client.headers["Authorization"] = "Bearer alice"
