import json
from datetime import timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from test_knowledge import TestVerifier
from test_knowledge import knowledge as knowledge_fixture  # noqa: F401

from knowledge_app.audit_models import ChangeContext, ChangeEvent, ChangeOutbox, ChangeReview
from knowledge_app.audit_service import AuditService
from knowledge_app.graph_contracts import AssertionInput, EntityInput
from knowledge_app.graph_service import GraphService
from knowledge_app.models import GraphClaim, GraphEvidence, now
from knowledge_app.service import owner_id
from knowledge_app.settings import Settings


def note(client, service):
    response = client.post(
        "/api/v1/knowledge",
        json={
            "title": "변경 이력",
            "text": "Oracle 원문 저장을 확인한다.",
            "origin_machine_id": "test-machine",
            "edit_origin": "HUMAN",
        },
    )
    assert response.status_code == 202, response.text
    result = response.json()
    assert service.process_one()
    return result


def drain(audit):
    for _ in range(100):
        if not audit.process_one():
            return
    raise AssertionError("Outbox did not converge")


def test_service_actor_request_machine_and_revision_history(knowledge_fixture):  # noqa: F811
    c, s, _ = knowledge_fixture
    response = c.post(
        "/api/v1/knowledge",
        json={
            "title": "변경",
            "text": "Oracle 기존 원문",
            "origin_machine_id": "machine-a",
            "edit_origin": "HUMAN",
        },
    )
    result = response.json()
    assert s.process_one()
    events = c.get(
        "/api/v1/changes", params={"table": "vk_revision", "target_id": result["revision_id"]}
    ).json()["items"]
    initial = next(e for e in events if e["action"] == "INSERT")
    assert initial["request_id"] == response.headers["x-request-id"]
    assert initial["actor_subject"] == "alice" and initial["machine_id"] == "machine-a"
    assert initial["operation"] == "SERVICE_CREATE"
    revised = c.post(
        f"/api/v1/knowledge/{result['knowledge_id']}/revisions",
        json={
            "text": "Oracle 새로운 원문",
            "expected_revision_id": result["revision_id"],
            "change_note": "확인된 보완",
        },
    ).json()
    assert s.process_one()
    changes = c.get("/api/v1/changes", params={"target_id": revised["revision_id"]}).json()["items"]
    assert any(e["reason"] == "확인된 보완" for e in changes)
    original = c.get(
        f"/api/v1/knowledge/{result['knowledge_id']}/revisions/{result['revision_id']}/content"
    ).json()
    assert original["text"] == "Oracle 기존 원문"
    with s.factory() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(ChangeContext)
                .where(ChangeContext.transaction_id.is_not(None))
            )
            == 0
        )


def test_raw_sql_snapshots_rollback_and_deleted_target_remain(knowledge_fixture):  # noqa: F811
    c, s, _ = knowledge_fixture
    idx = c.post("/api/v1/indexes", json={"key": "audit", "title": "이전 제목", "summary": "설명"}).json()
    with s.factory() as session:
        baseline = session.scalar(select(func.count()).select_from(ChangeEvent))
        session.execute(
            text("UPDATE vk_index SET title=:title WHERE id=:id"), {"title": "롤백 제목", "id": idx["id"]}
        )
        assert session.scalar(select(func.count()).select_from(ChangeEvent)) == baseline + 1
        session.rollback()
        assert session.scalar(select(func.count()).select_from(ChangeEvent)) == baseline
    with s.factory.begin() as session:
        session.execute(
            text("UPDATE vk_index SET body=:body,title=:title WHERE id=:id"),
            {"body": "한글 장문 " * 10000, "title": "새 제목", "id": idx["id"]},
        )
    changes = c.get("/api/v1/changes", params={"target_id": idx["id"]}).json()["items"]
    change = next(x for x in changes if x["source"] == "DIRECT_SQL")
    detail = c.get("/api/v1/changes/" + change["id"]).json()
    assert detail["before"]["title"] == "이전 제목"
    assert detail["after"]["title"] == "새 제목" and len(detail["after"]["body"]) > 4000
    # No memberships/history rows are deleted: remove a standalone directly-inserted entity instead.
    owner = owner_id(TestVerifier().verify("alice"))
    with s.factory.begin() as session:
        session.execute(
            text(
                "INSERT INTO vk_g_entity (id,owner_id,scope,identity_hash,identity_key,label,kind,aliases_json,created_at) VALUES ('raw',:owner,'global','raw','raw','직접 등록','THING','[]',CURRENT_TIMESTAMP)"
            ),
            {"owner": owner},
        )
        session.execute(text("DELETE FROM vk_g_entity WHERE id='raw'"))
    deleted = c.get("/api/v1/changes", params={"target_id": "raw"}).json()["items"]
    event = next(e for e in deleted if e["action"] == "DELETE")
    assert c.get("/api/v1/changes/" + event["id"]).json()["before"]["label"] == "직접 등록"


def test_append_only_identity_owner_isolation_and_no_context_leak(knowledge_fixture):  # noqa: F811
    c, s, _ = knowledge_fixture
    ids = note(c, s)
    events = c.get("/api/v1/changes").json()["items"]
    eid = events[0]["id"]
    for sql, params in [
        ("DELETE FROM vk_change_event WHERE id=:id", {"id": eid}),
        ("UPDATE vk_change_event SET action='DELETE' WHERE id=:id", {"id": eid}),
        ("UPDATE vk_item SET owner_id='other' WHERE id=:id", {"id": ids["knowledge_id"]}),
    ]:
        with s.factory() as session:
            with pytest.raises(IntegrityError):
                session.execute(text(sql), params)
            session.rollback()
    with s.factory.begin() as session:
        session.execute(
            text("UPDATE vk_item SET title=:title WHERE id=:id"),
            {"title": "직접 수정", "id": ids["knowledge_id"]},
        )
    assert any(
        e["source"] == "DIRECT_SQL"
        for e in c.get("/api/v1/changes", params={"target_id": ids["knowledge_id"]}).json()["items"]
    )
    c.headers["Authorization"] = "Bearer bob"
    assert c.get("/api/v1/changes").json()["items"] == []
    assert c.get("/api/v1/changes/" + eid).status_code == 404
    assert c.post("/api/v1/changes/" + eid + "/retry").status_code == 404


def test_direct_changes_review_once_resolution_and_owner(knowledge_fixture):  # noqa: F811
    c, s, _ = knowledge_fixture
    ids = note(c, s)
    audit = AuditService(s.factory)
    with s.factory.begin() as session:
        session.execute(
            text("UPDATE vk_item SET title=:title WHERE id=:id"),
            {"title": "수동 변경", "id": ids["knowledge_id"]},
        )
    drain(audit)
    assert not audit.process_one()
    reviews = c.get("/api/v1/change-reviews").json()["items"]
    assert len(reviews) == 1 and reviews[0]["reason"] == "DIRECT_SQL_CHANGE"
    rid = reviews[0]["id"]
    c.headers["Authorization"] = "Bearer bob"
    assert not c.get("/api/v1/change-reviews").json()["items"]
    assert c.post(f"/api/v1/change-reviews/{rid}/resolve", json={"note": "확인"}).status_code == 404
    c.headers["Authorization"] = "Bearer alice"
    assert c.post(f"/api/v1/change-reviews/{rid}/resolve", json={"note": "  "}).status_code == 400
    assert (
        c.post(f"/api/v1/change-reviews/{rid}/resolve", json={"note": "원문과 대조 완료"}).json()["status"]
        == "RESOLVED"
    )
    assert c.post(f"/api/v1/change-reviews/{rid}/resolve", json={"note": "원문과 대조 완료"}).json()[
        "unchanged"
    ]
    assert len(c.get("/api/v1/change-reviews?status=RESOLVED").json()["items"]) == 1


def test_failed_effect_rolls_back_and_retry_preserves_attempts(knowledge_fixture, monkeypatch):  # noqa: F811
    c, s, _ = knowledge_fixture
    note(c, s)
    audit = AuditService(s.factory)
    with s.factory.begin() as session:
        first = session.scalar(
            select(ChangeOutbox).order_by(ChangeOutbox.available_at, ChangeOutbox.event_id)
        )
        eid = first.event_id
        for row in session.scalars(select(ChangeOutbox)):
            if row.event_id != eid:
                row.available_at = now() + timedelta(days=1)
    original = audit.consume

    def broken(session, event):
        audit.review(session, event, "test", event.target_id, "TEST_ROLLBACK")
        session.flush()
        raise RuntimeError("sensitive provider detail")

    monkeypatch.setattr(audit, "consume", broken)
    for _ in range(5):
        with s.factory.begin() as session:
            session.get(ChangeOutbox, eid).available_at = now() - timedelta(seconds=1)
        assert audit.process_one()
    with s.factory() as session:
        row = session.get(ChangeOutbox, eid)
        assert row.status == "FAILED" and row.attempts == 5
        assert session.scalar(select(func.count()).select_from(ChangeReview)) == 0
    detail = c.get("/api/v1/changes/" + eid).json()
    assert "sensitive" not in json.dumps(detail)
    assert c.post("/api/v1/changes/" + eid + "/retry").json()["attempts"] == 5
    monkeypatch.setattr(audit, "consume", original)
    assert audit.process_one()
    with s.factory() as session:
        assert session.get(ChangeOutbox, eid).status == "DONE"
        assert session.get(ChangeOutbox, eid).attempts == 6


def test_new_revision_marks_rdf_evidence_for_review_without_rewriting(knowledge_fixture):  # noqa: F811
    c, s, _ = knowledge_fixture
    ids = note(c, s)
    actor = TestVerifier().verify("alice")
    graph = GraphService(s.factory, Settings(_env_file=None, workflow_rdf_enabled=True))
    a = graph.entity(actor, EntityInput(identity_key="a", label="원문 저장"))
    b = graph.entity(actor, EntityInput(identity_key="b", label="결과 확인"))
    claim = graph.assertion(
        actor,
        AssertionInput(
            subject_id=a["id"],
            object_id=b["id"],
            predicate="precedes",
            verified=True,
            evidence=[
                {
                    "knowledge_id": ids["knowledge_id"],
                    "revision_id": ids["revision_id"],
                    "quote": "Oracle 원문 저장을 확인한다.",
                }
            ],
        ),
    )
    audit = AuditService(s.factory)
    drain(audit)
    updated = c.post(
        f"/api/v1/knowledge/{ids['knowledge_id']}/revisions",
        json={"text": "Oracle 최신 절차는 추가 확인이 필요하다.", "expected_revision_id": ids["revision_id"]},
    ).json()
    assert s.process_one()
    drain(audit)
    reviews = c.get("/api/v1/change-reviews").json()["items"]
    assert any(
        x["target_id"] == claim["assertion_id"] and x["reason"] == "SOURCE_REVISION_CHANGED" for x in reviews
    )
    with s.factory() as session:
        assert session.get(GraphClaim, claim["assertion_id"]).current_version_id == claim["version_id"]
        assert (
            session.scalar(
                select(GraphEvidence.revision_id).where(GraphEvidence.version_id == claim["version_id"])
            )
            == ids["revision_id"]
        )
    assert (
        c.get(
            f"/api/v1/knowledge/{ids['knowledge_id']}/references?revision_id={updated['revision_id']}"
        ).json()["rdf"]["status"]
        == "READY"
    )


def test_two_consumers_do_not_duplicate_effects(knowledge_fixture):  # noqa: F811
    from concurrent.futures import ThreadPoolExecutor

    c, s, _ = knowledge_fixture
    ids = note(c, s)
    with s.factory.begin() as session:
        session.execute(
            text("UPDATE vk_item SET title='동시 처리' WHERE id=:id"), {"id": ids["knowledge_id"]}
        )
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [pool.submit(drain, AuditService(s.factory)) for _ in range(2)]
        for result in results:
            result.result()
    with s.factory() as session:
        rows = list(session.scalars(select(ChangeOutbox)))
        assert rows and all(r.status == "DONE" and r.attempts == 1 for r in rows)
        assert session.scalar(select(func.count()).select_from(ChangeReview)) == 1


def test_audit_write_failure_rolls_back_source(knowledge_fixture):  # noqa: F811
    c, s, _ = knowledge_fixture
    with s.factory.begin() as session:
        session.execute(
            text(
                "CREATE TRIGGER reject_outbox BEFORE INSERT ON vk_change_outbox BEGIN SELECT RAISE(ABORT,'TEST_AUDIT_FAILURE'); END"
            )
        )
    response = c.post("/api/v1/knowledge", json={"title": "감사 실패 원자성", "text": "Oracle 원문"})
    assert response.status_code >= 400
    with s.factory() as session:
        assert session.scalar(text("SELECT COUNT(*) FROM vk_item")) == 0
        assert session.scalar(select(func.count()).select_from(ChangeEvent)) == 0
        assert session.scalar(select(func.count()).select_from(ChangeContext)) == 0
