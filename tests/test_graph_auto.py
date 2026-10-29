import json
from datetime import timedelta
from unittest.mock import patch

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from test_knowledge import knowledge as knowledge_fixture  # noqa: F401

from knowledge_app.graph_auto_contracts import AutoGraphSettings, Extraction
from knowledge_app.graph_auto_models import ExtractionRun, GraphProposal
from knowledge_app.models import GraphEntity, now

TEXT = "주문 API는 주문 DB를 사용한다."
PAYLOAD = dict(
    entities=[
        dict(key="a", label="주문 API", kind="service", mention="주문 API"),
        dict(key="b", label="주문 DB", kind="resource", mention="주문 DB"),
    ],
    relations=[dict(subject="a", predicate="uses", object="b", quote=TEXT)],
)


class Extractor:
    def extract(self, content, context):
        return Extraction.model_validate(PAYLOAD)


class Router:
    def __init__(self, action="graph_extract"):
        self.action, self.calls = action, 0

    async def decide(self, request):
        self.calls += 1
        return dict(action=self.action, reason="test", model_called=False)


def setup(knowledge, text=TEXT, kind="FACT"):
    client, service, _ = knowledge
    service.settings.workflow_rdf_enabled = True
    source = client.post(
        "/api/v1/knowledge", json=dict(title="자동 관계", text=text, memory_kind=kind, scope="project:test")
    ).json()
    assert service.process_one()
    auto = client.app.state.auto_graph
    auto.config = AutoGraphSettings(_env_file=None, enabled=True, model="test")
    auto.extractor, auto.router = Extractor(), Router()
    return client, service, auto, source


def proposals(client):
    return client.get("/api/v1/graph/proposals").json()["items"]


def approve(client, proposal, **overrides):
    command = dict(
        decision="approve",
        note="원문과 개체 식별을 확인함",
        subject={"identity_key": "service:orders"},
        object={"identity_key": "db:orders"},
    )
    command.update(overrides)
    return client.post("/api/v1/graph/proposals/" + proposal["id"] + "/review", json=command)


def test_extract_review_graph_and_idempotency(knowledge_fixture):  # noqa: F811
    client, service, auto, source = setup(knowledge_fixture)
    assert auto.process_one()
    assert not auto.process_one()
    row = proposals(client)[0]
    assert row["candidate"]["quote"] == TEXT
    assert client.post("/api/v1/graph/search", json={}).json()["edges"] == []
    result = approve(client, row)
    assert result.status_code == 200, result.text
    assert approve(client, row).json()["assertion_id"] == result.json()["assertion_id"]
    assert len(client.post("/api/v1/graph/search", json={}).json()["edges"]) == 1
    second = client.post(
        "/api/v1/knowledge", json=dict(title="다른 근거", text=TEXT, scope="project:test")
    ).json()
    assert service.process_one()
    assert auto.process_one()
    row2 = next(p for p in proposals(client) if p["revision_id"] == second["revision_id"])
    assert approve(client, row2).json()["assertion_id"] == result.json()["assertion_id"]
    assert len(client.post("/api/v1/graph/search", json={}).json()["edges"][0]["evidence"]) == 2


def test_owner_isolation_reject_and_stale(knowledge_fixture):  # noqa: F811
    client, service, auto, source = setup(knowledge_fixture)
    assert auto.process_one()
    row = proposals(client)[0]
    client.headers["Authorization"] = "Bearer bob"
    assert proposals(client) == []
    assert approve(client, row).status_code == 404
    client.headers["Authorization"] = "Bearer alice"
    result = client.post(
        "/api/v1/knowledge/" + source["knowledge_id"] + "/revisions",
        json=dict(expected_revision_id=source["revision_id"], text="변경된 원문", change_note="수정"),
    )
    assert result.status_code == 202
    assert service.process_one()
    assert proposals(client)[0]["status"] == "STALE"
    assert approve(client, row).status_code == 409


def test_invalid_evidence_retry_and_secrets_not_exposed(knowledge_fixture):  # noqa: F811
    client, _, auto, _ = setup(knowledge_fixture, text="다른 내용")
    auto.extractor.extract = lambda *args: (_ for _ in ()).throw(RuntimeError("secret-provider-message"))
    for attempt in range(5):
        assert auto.process_one()
        with auto.factory.begin() as session:
            run = session.scalar(select(ExtractionRun))
            assert run.attempts == attempt + 1
            run.available_at = now() - timedelta(seconds=1)
    runs = client.get("/api/v1/graph/extraction/runs").json()["items"]
    assert runs[0]["status"] == "FAILED"
    assert runs[0]["error_code"] == "GRAPH_EXTRACTION_FAILED"
    assert "secret-provider-message" not in json.dumps(runs)
    assert proposals(client) == []
    assert client.post("/api/v1/graph/extraction/runs/" + runs[0]["id"] + "/retry").status_code == 200


def test_required_procedure_overrides_skip(knowledge_fixture):  # noqa: F811
    client, _, auto, _ = setup(knowledge_fixture, kind="PROCEDURE")
    auto.router = Router("skip")
    assert auto.process_one()
    assert auto.router.calls == 0
    assert len(proposals(client)) == 1


def test_optional_skip_and_lease_recovery(knowledge_fixture):  # noqa: F811
    client, _, auto, source = setup(knowledge_fixture)
    run = client.post("/api/v1/graph/extraction/knowledge/" + source["knowledge_id"]).json()
    with auto.factory.begin() as session:
        row = session.get(ExtractionRun, run["id"])
        row.force_extract = 0
        row.status = "RUNNING"
        row.lease_token = "old"
        row.available_at = now() - timedelta(seconds=1)
    auto.router = Router("skip")
    assert auto.process_one()
    assert client.get("/api/v1/graph/extraction/runs").json()["items"][0]["status"] == "SKIPPED"
    auto.finish(row.owner_id, run["id"], "old", "DONE", None, Extraction.model_validate(PAYLOAD))
    assert proposals(client) == []


def test_approval_rolls_back_new_entities_when_assertion_fails(knowledge_fixture):  # noqa: F811
    client, _, auto, _ = setup(knowledge_fixture)
    assert auto.process_one()
    row = proposals(client)[0]
    with patch("knowledge_app.graph_auto_service.GraphService.assertion", side_effect=ValueError("test")):
        assert approve(client, row).status_code == 500
    with auto.factory() as session:
        assert list(session.scalars(select(GraphEntity))) == []
        assert session.get(GraphProposal, row["id"]).status == "PENDING"


def test_schema_rejects_invalid_pattern_and_remote_default():
    payload = json.loads(json.dumps(PAYLOAD))
    payload["relations"][0]["predicate"] = "invented"
    with pytest.raises(ValidationError):
        Extraction.model_validate(payload)
    with pytest.raises(ValidationError):
        AutoGraphSettings(_env_file=None, url="https://example.org/v1")


def test_auto_existing_requires_exact_canonical_ids(knowledge_fixture):  # noqa: F811
    text = "service:orders --uses--> db:orders"
    client, _, auto, _ = setup(knowledge_fixture, text=text)
    a = client.post(
        "/api/v1/graph/entities",
        json=dict(scope="project:test", identity_key="service:orders", label="주문 API", kind="service"),
    ).json()["id"]
    b = client.post(
        "/api/v1/graph/entities",
        json=dict(scope="project:test", identity_key="db:orders", label="주문 DB", kind="resource"),
    ).json()["id"]
    payload = json.loads(json.dumps(PAYLOAD))
    payload["entities"][0].update(mention="service:orders", existing_id=a)
    payload["entities"][1].update(mention="db:orders", existing_id=b)
    payload["relations"][0]["quote"] = text
    auto.config.policy = "auto_existing"
    with patch.object(auto.extractor, "extract", return_value=Extraction.model_validate(payload)):
        assert auto.process_one()
    assert proposals(client)[0]["status"] == "APPROVED"
    assert len(client.post("/api/v1/graph/search", json={}).json()["edges"]) == 1


def test_explicit_extract_overrides_kevs_skip(knowledge_fixture):  # noqa: F811
    client, _, auto, source = setup(knowledge_fixture)
    auto.router = Router("skip")
    assert auto.process_one()
    assert client.get("/api/v1/graph/extraction/runs").json()["items"][0]["status"] == "SKIPPED"
    assert (
        client.post("/api/v1/graph/extraction/knowledge/" + source["knowledge_id"]).json()["status"]
        == "PENDING"
    )
    assert auto.process_one()
    assert len(proposals(client)) == 1


def test_source_changed_during_extraction_is_stale(knowledge_fixture):  # noqa: F811
    client, service, auto, source = setup(knowledge_fixture)

    def extract(content, context):
        client.post(
            "/api/v1/knowledge/" + source["knowledge_id"] + "/revisions",
            json=dict(expected_revision_id=source["revision_id"], text="새로운 내용", change_note="변경"),
        )
        assert service.process_one()
        return Extraction.model_validate(PAYLOAD)

    with patch.object(auto.extractor, "extract", side_effect=extract):
        assert auto.process_one()
    assert proposals(client) == []
    assert client.get("/api/v1/graph/extraction/runs").json()["items"][0]["status"] == "STALE"


def test_model_endpoint_normalization_and_partial_rejection():
    from knowledge_app.graph_auto_extractor import normalize_extraction

    payload = json.loads(json.dumps(PAYLOAD))
    payload["relations"][0].update(subject="주문 API", object="주문 DB")
    payload["relations"].append(dict(subject="missing", predicate="uses", object="b", quote=TEXT))
    result = normalize_extraction(json.dumps(payload))
    assert result.relations[0].subject == "a"
    assert result.relations[0].object == "b"
    assert result.rejected_relations == 1


def test_ambiguous_label_never_normalizes_identity():
    from knowledge_app.graph_auto_extractor import normalize_extraction

    payload = json.loads(json.dumps(PAYLOAD))
    payload["entities"].append(dict(key="a2", label="주문 API", kind="service", mention="주문 API"))
    payload["relations"][0]["subject"] = "주문 API"
    result = normalize_extraction(json.dumps(payload))
    assert result.relations == []
    assert result.rejected_relations == 1


def test_invalid_evidence_is_excluded_without_losing_valid_relations(knowledge_fixture):  # noqa: F811
    client, _, auto, _ = setup(knowledge_fixture)
    payload = json.loads(json.dumps(PAYLOAD))
    payload["relations"].append(
        dict(subject="a", predicate="uses", object="b", quote="주문 API는 다른 주문 DB를 사용한다.")
    )
    with patch.object(auto.extractor, "extract", return_value=Extraction.model_validate(payload)):
        assert auto.process_one()
    assert len(proposals(client)) == 1
    run = client.get("/api/v1/graph/extraction/runs").json()["items"][0]
    assert run["status"] == "PARTIAL"
    assert run["routing"]["rejected_relations"] == 1


def project_payload():
    return dict(
        entities=[
            dict(key="ux", label="Cafesto UX", kind="project_area", mention="UX"),
            dict(key="cafesto", label="Cafesto", kind="project", mention="Cafesto"),
            dict(key="base", label="TypeScript Foundation", kind="template", mention="TypeScript Foundation"),
        ],
        relations=[
            dict(subject="ux", predicate="part_of", object="cafesto", quote="Cafesto의 UX를 개선했다."),
            dict(
                subject="cafesto",
                predicate="created_from",
                object="base",
                quote="Cafesto는 TypeScript Foundation 템플릿을 복사해 생성했다.",
            ),
        ],
    )


def test_project_area_and_template_are_distinct_from_dependency():
    from knowledge_app.graph_auto_extractor import verified_extraction

    payload = project_payload()
    result = verified_extraction(
        Extraction.model_validate(payload),
        json.dumps(
            {"verdicts": [{"index": 0, "verdict": "supported"}, {"index": 1, "verdict": "supported"}]}
        ),
    )
    assert [r.predicate for r in result.relations] == ["part_of", "created_from"]
    payload["relations"][1]["predicate"] = "depends_on"
    with pytest.raises(ValidationError):
        Extraction.model_validate(payload)


@pytest.mark.parametrize("verdict", ["unsupported", "uncertain"])
def test_semantic_rejection_drops_project_area_without_anchor(verdict):
    from knowledge_app.graph_auto_extractor import verified_extraction

    result = verified_extraction(
        Extraction.model_validate(project_payload()),
        json.dumps({"verdicts": [{"index": 0, "verdict": verdict}, {"index": 1, "verdict": "supported"}]}),
    )
    assert [e.key for e in result.entities] == ["cafesto", "base"]
    assert result.rejected_relations == 1


@pytest.mark.parametrize(
    "verdicts",
    [
        [],
        [{"index": 0, "verdict": "supported"}] * 2,
        [{"index": 0, "verdict": "supported"}, {"index": 3, "verdict": "supported"}],
    ],
)
def test_verifier_missing_duplicate_or_unknown_index_fails_closed(verdicts):
    from knowledge_app.graph_auto_extractor import verified_extraction

    with pytest.raises(ValueError):
        verified_extraction(Extraction.model_validate(project_payload()), json.dumps({"verdicts": verdicts}))


def test_generic_or_other_project_ux_cannot_be_anchored():
    from knowledge_app.graph_auto_extractor import verified_extraction

    for label in ["UX", "OtherProject UX"]:
        payload = project_payload()
        payload["entities"][0]["label"] = label
        result = verified_extraction(
            Extraction.model_validate(payload),
            json.dumps(
                {"verdicts": [{"index": 0, "verdict": "supported"}, {"index": 1, "verdict": "supported"}]}
            ),
        )
        assert all(e.kind != "project_area" for e in result.entities)


@pytest.mark.parametrize(
    "subject_kind,object_kind", [("action", "action"), ("service", "task"), ("task", "task")]
)
def test_word_and_workflow_pairs_are_not_structural_membership(subject_kind, object_kind):
    payload = json.loads(json.dumps(PAYLOAD))
    payload["entities"][0]["kind"] = subject_kind
    payload["entities"][1]["kind"] = object_kind
    payload["relations"][0]["predicate"] = "part_of"
    with pytest.raises(ValidationError):
        Extraction.model_validate(payload)


def test_old_pending_candidates_require_reextraction(knowledge_fixture):  # noqa: F811
    client, service, auto, _ = setup(knowledge_fixture)
    assert auto.process_one()
    row = proposals(client)[0]
    with auto.factory() as session:
        run = session.scalar(select(ExtractionRun))
        run.schema_version = "operations-v1"
        session.commit()
    assert proposals(client)[0]["status"] == "LEGACY"
    assert approve(client, row).status_code == 409
    assert client.post("/api/v1/graph/search", json={}).json()["edges"] == []


def test_http_extractor_uses_separate_semantic_review():
    from knowledge_app.graph_auto_extractor import HTTPExtractor

    extractor = HTTPExtractor(AutoGraphSettings(_env_file=None, model="test"))
    with patch.object(
        extractor,
        "complete",
        side_effect=[json.dumps(PAYLOAD), json.dumps({"verdicts": [{"index": 0, "verdict": "unsupported"}]})],
    ) as complete:
        result = extractor.extract(TEXT, [])
    assert complete.call_count == 2
    assert not result.relations
    assert result.rejected_relations == 1


def test_auto_verified_creates_connections_without_user_fields(knowledge_fixture):  # noqa: F811
    client, service, auto, _ = setup(knowledge_fixture)
    auto.config.policy = "auto_verified"
    assert auto.process_one()
    row = proposals(client)[0]
    assert row["status"] == "APPROVED"
    assert row["review_note"].startswith("AUTO: auto_verified")
    assert len(client.post("/api/v1/graph/search", json={}).json()["edges"]) == 1
    second = client.post(
        "/api/v1/knowledge", json=dict(title="추가 근거", text=TEXT, scope="project:test")
    ).json()
    assert service.process_one()
    assert auto.process_one()
    row2 = next(p for p in proposals(client) if p["revision_id"] == second["revision_id"])
    assert row2["assertion_id"] == row["assertion_id"]
    with auto.factory() as session:
        assert len(list(session.scalars(select(GraphEntity)))) == 2


def test_auto_verified_ambiguous_names_remain_pending(knowledge_fixture):  # noqa: F811
    client, _, auto, _ = setup(knowledge_fixture)
    for key in ["orders:a", "orders:b"]:
        client.post(
            "/api/v1/graph/entities",
            json=dict(scope="project:test", identity_key=key, label="주문 API", kind="service"),
        )
    auto.config.policy = "auto_verified"
    assert auto.process_one()
    assert proposals(client)[0]["status"] == "PENDING"
    assert client.post("/api/v1/graph/search", json={}).json()["edges"] == []
    assert not auto.process_one()  # No endless retry of an ambiguous result.


def test_auto_verified_publishes_existing_completed_candidates(knowledge_fixture):  # noqa: F811
    client, _, auto, _ = setup(knowledge_fixture)
    assert auto.process_one()
    assert proposals(client)[0]["status"] == "PENDING"
    auto.config.policy = "auto_verified"
    assert auto.process_one()
    assert proposals(client)[0]["status"] == "APPROVED"
    assert not auto.process_one()


@pytest.mark.parametrize("correction", ["RETRACTED", "depends_on"])
def test_user_correction_preserves_history_and_is_not_reintroduced(knowledge_fixture, correction):  # noqa: F811
    client, service, auto, source = setup(knowledge_fixture)
    auto.config.policy = "auto_verified"
    assert auto.process_one()
    row = proposals(client)[0]
    history = client.get(f"/api/v1/graph/assertions/{row['assertion_id']}/history").json()
    version = next(v for v in history["versions"] if v["recorded_to"] is None)
    expected = version.pop("version_id")
    version.pop("recorded_to")
    version.pop("recorded_from")
    version.update(expected_version_id=expected, change_note="사용자 수정")
    if correction == "RETRACTED":
        version["status"] = "RETRACTED"
    else:
        version["predicate"] = correction
    response = client.put(f"/api/v1/graph/assertions/{row['assertion_id']}", json=version)
    assert response.status_code == 200, response.text
    assert client.put(f"/api/v1/graph/assertions/{row['assertion_id']}", json=version).status_code == 409
    history = client.get(f"/api/v1/graph/assertions/{row['assertion_id']}/history").json()
    assert len(history["versions"]) == 2
    # Simulate a new extraction run for the same source; old proposal and graph history stay intact.
    with auto.factory() as session:
        run = session.scalar(select(ExtractionRun))
        run.run_key = "old-run"
        run.schema_version = "previous"
        session.commit()
    assert client.post("/api/v1/graph/extraction/knowledge/" + source["knowledge_id"]).status_code == 200
    assert auto.process_one()
    new = next(p for p in proposals(client) if p["id"] != row["id"])
    assert new["status"] == "PENDING"
    edges = client.post("/api/v1/graph/search", json={}).json()["edges"]
    assert len(edges) == (0 if correction == "RETRACTED" else 1)
    assert all(e["predicate"] != "uses" for e in edges)


def test_backfill_uses_authenticated_request_when_old_author_audit_missing(knowledge_fixture):  # noqa: F811
    from knowledge_app.audit_models import ChangeContext

    client, _, auto, source = setup(knowledge_fixture)
    assert auto.process_one()
    with auto.factory() as session:
        for context in session.scalars(select(ChangeContext)):
            context.actor_subject = None
        session.commit()
    auto.config.policy = "auto_verified"
    assert auto.process_one()
    assert proposals(client)[0]["status"] == "PENDING"
    run = client.get("/api/v1/graph/extraction/runs").json()["items"][0]
    assert run["routing"]["auto_result"]["reason"] == "REQUEST_ACTOR_REQUIRED"
    result = client.post("/api/v1/graph/extraction/knowledge/" + source["knowledge_id"])
    assert result.status_code == 200
    assert "requested_by" not in result.json()["routing"]
    assert auto.process_one()
    assert proposals(client)[0]["status"] == "APPROVED"
    run = client.get("/api/v1/graph/extraction/runs").json()["items"][0]
    assert run["routing"]["auto_result"]["connected"] == 1


def test_component_can_use_resource():
    from knowledge_app.graph_auto_extractor import normalize_extraction

    payload = json.loads(json.dumps(PAYLOAD))
    payload["entities"][0]["kind"] = "component"
    result = normalize_extraction(json.dumps(payload))
    assert len(result.relations) == 1
    assert result.rejected_relations == 0
