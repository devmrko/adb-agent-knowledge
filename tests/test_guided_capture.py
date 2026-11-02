from test_graph_operations import ops  # noqa: F401
from test_knowledge import knowledge as knowledge_fixture  # noqa: F401
from test_shared_graph import entity, source


def draft(evidence, version=0):
    return dict(
        revision_id=evidence["revision_id"],
        expected_version=version,
        summary="기존 자료의 의미를 확인",
        hypotheses=["별칭의 적용 범위는 미확인"],
        questions=[
            dict(
                key="scope",
                question="현재 운영만의 별칭인가요?",
                reason="환경을 잘못 병합하지 않기 위해",
                quote=evidence["quote"],
                options=["운영만", "공통"],
            )
        ],
    )


def test_persist_resume_answer_publish_and_audit(ops):  # noqa: F811
    client, service, ev, eid = ops
    path = f"/api/v1/graph/reviews/{ev['knowledge_id']}/capture"
    assert client.get(path).json()["capture"] is None
    saved = client.post(path, json=draft(ev))
    assert saved.status_code == 200, saved.text
    assert saved.json()["published"] is False
    assert saved.json()["capture"]["status"] == "WAITING_INPUT"
    assert client.post(path, json=draft(ev)).status_code == 409
    assert client.post(path, json=draft(ev, 1)).status_code == 409
    body = dict(
        revision_id=ev["revision_id"], expected_version=1, status="COMPLETE", outcome="NONE", note="test"
    )
    assert client.post(path.removesuffix("/capture"), json=body).status_code == 409
    answer = dict(
        revision_id=ev["revision_id"],
        expected_version=1,
        question_key="scope",
        text="나중에 확인",
        disposition="deferred",
    )
    assert client.post(path + "/answers", json=answer).status_code == 200
    assert client.get(path).json()["capture"]["pending_question_keys"] == ["scope"]
    answer.update(
        expected_version=2, text="인증 서비스는 운영 데이터베이스를 사용한다.", disposition="answered"
    )
    result = client.post(path + "/answers", json=answer)
    assert result.status_code == 200, result.text
    assert result.json()["capture"]["status"] == "NEEDS_RECONCILIATION"
    assert client.post(path + "/answers", json=answer).status_code == 409
    # HTTP GET opens a fresh unit of work; state is not held in the conversation.
    resumed = client.get(path).json()
    assert resumed["capture"]["questions"][0]["answer"]["text"] == answer["text"]
    # User answer becomes its own source before it can support a graph assertion.
    confirmation = source(client, service, answer["text"], "project:auth")
    target = entity(client, "production-db", "project:auth", "운영 데이터베이스")
    published = client.post(
        "/api/v1/graph/assertions",
        json=dict(
            scope="project:auth",
            subject_id=eid,
            object_id=target,
            predicate="uses",
            verified=True,
            evidence=[confirmation],
        ),
    )
    assert published.status_code == 200, published.text
    # Original review has no assertion on its own revision; answer source is separate.
    assert client.post(path.removesuffix("/capture"), json={**body, "expected_version": 3}).status_code == 200
    history = client.get("/api/v1/graph/operations/" + resumed["review"]["id"]).json()["items"]
    captures = [r for r in history if r["kind"] == "CAPTURE"]
    assert [r["version"] for r in captures] == [3, 2, 1]
    assert captures[-1]["snapshot"]["questions"][0]["answer"] is None
    audit = client.get(
        "/api/v1/changes", params={"table": "vk_g_review", "target_id": resumed["review"]["id"]}
    ).json()["items"]
    assert any(x["operation"] == "GRAPH_CAPTURE" and x["actor_subject"] == "alice" for x in audit)


def test_stale_revision_retirement_owner_and_validation(ops):  # noqa: F811
    client, service, ev, _ = ops
    path = f"/api/v1/graph/reviews/{ev['knowledge_id']}/capture"
    invalid = draft(ev)
    invalid["questions"][0]["quote"] = "없는 문장"
    assert client.post(path, json=invalid).status_code == 400
    assert client.get(path).json()["review"]["version"] == 0
    assert client.post(path, json=draft(ev)).status_code == 200
    answer = dict(revision_id=ev["revision_id"], expected_version=1, question_key="scope", text="공통")
    client.headers["Authorization"] = "Bearer bob"
    assert client.get(path).status_code == 404
    assert client.post(path + "/answers", json=answer).status_code == 404
    client.headers["Authorization"] = "Bearer alice"
    updated = client.post(
        f"/api/v1/knowledge/{ev['knowledge_id']}/revisions",
        json={"expected_revision_id": ev["revision_id"], "text": ev["quote"] + " 변경됨"},
    )
    assert updated.status_code < 300
    assert service.process_one()
    assert client.get(path).json()["capture"] is None
    old = client.get(path, params={"revision_id": ev["revision_id"]}).json()
    assert not old["source_current"] and old["capture"]["pending_question_keys"]
    assert client.post(path + "/answers", json=answer).status_code == 409
    client.post(f"/api/v1/knowledge/{ev['knowledge_id']}/retire", json={"reason": "테스트"})
    assert client.post(path + "/answers", json=answer).status_code == 409


def test_tasteby_current_practice_not_mandatory_policy(ops):  # noqa: F811
    client, service, _, _ = ops
    ev = source(
        client,
        service,
        "Tasteby 백오피스에서 가게 정보를 수정하고 게시한다. 지금은 내가 확인하고 올린다. 점주가 직접 수정하게 하고 싶다.",
        "project:tasteby",
    )
    path = f"/api/v1/graph/reviews/{ev['knowledge_id']}/capture"
    command = draft(ev)
    command["summary"] = "현재 직접 게시하며 점주 수정은 개선 목표다."
    command["hypotheses"] = ["직접 확인이 필수 승인 규칙인지는 미확인"]
    command["questions"] = [
        dict(
            key="approval",
            question="필수 승인 절차인가요, 현재 담당 방식인가요?",
            reason="현재 관행을 필수 규칙으로 저장하지 않기 위해",
            quote="지금은 내가 확인하고 올린다.",
        )
    ]
    assert client.post(path, json=command).status_code == 200
    result = client.post(
        path + "/answers",
        json=dict(
            revision_id=ev["revision_id"],
            expected_version=1,
            question_key="approval",
            text="현재 담당 방식일 뿐 필수 승인 절차는 아니다.",
        ),
    )
    assert result.status_code == 200
    assert result.json()["published"] is False
    assert client.get(path).json()["capture"]["status"] == "NEEDS_RECONCILIATION"
    # No inferred policy is silently published as an assertion.
    graph = client.post("/api/v1/graph/search", json={"knowledge_id": ev["knowledge_id"]}).json()
    assert not graph["edges"]
