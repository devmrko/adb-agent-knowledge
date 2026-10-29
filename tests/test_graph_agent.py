"""Agent mode must work without a generation provider or background extraction."""

from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import func, select
from test_graph_auto import TEXT, setup
from test_knowledge import knowledge as knowledge_fixture  # noqa: F401

from knowledge_app.graph_auto_contracts import AutoGraphSettings
from knowledge_app.graph_auto_models import ExtractionRun
from knowledge_app.graph_auto_service import AutoGraphService
from knowledge_app.models import Item


def test_agent_mode_never_constructs_or_runs_generation(knowledge_fixture):  # noqa: F811
    client, service, auto, source = setup(knowledge_fixture)
    with patch("knowledge_app.graph_auto_service.ModelExtractor", side_effect=AssertionError("LLM")):
        agent = AutoGraphService(
            auto.factory,
            service.settings,
            config=AutoGraphSettings(_env_file=None, enabled=True, model=""),
        )
    assert agent.extractor is None
    assert agent.schema()["mode"] == "agent"
    assert not agent.schema()["enabled"]
    assert not agent.process_one()
    auto.config = agent.config
    response = client.post(f"/api/v1/graph/extraction/knowledge/{source['knowledge_id']}")
    assert response.status_code == 503
    assert "GRAPH_AGENT_EXTRACTION_REQUIRED" in response.text
    assert client.post(f"/api/v1/graph/extraction/runs/{uuid4()}/retry").status_code == 503
    with auto.factory() as session:
        assert session.scalar(select(func.count()).select_from(ExtractionRun)) == 0


def test_prepare_exact_revision_bounds_ownership_and_staleness(knowledge_fixture):  # noqa: F811
    client, service, auto, source = setup(knowledge_fixture, text=TEXT * 100)
    auto.config = AutoGraphSettings(_env_file=None)
    path = f"/api/v1/graph/extraction/knowledge/{source['knowledge_id']}/prepare"
    payload = {"expected_revision_id": source["revision_id"], "max_chars": 1000}
    result = client.post(path, json=payload)
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["revision_id"] == source["revision_id"]
    assert data["text"] == (TEXT * 100)[:1000]
    assert data["next_offset"] == 1000
    assert not data["writes_performed"]
    assert data["schema"]["mode"] == "agent"
    assert client.post(path, json={"max_chars": 999}).status_code == 400
    assert client.post(path, json={"expected_revision_id": str(uuid4())}).status_code == 409
    client.headers["Authorization"] = "Bearer bob"
    assert client.post(path, json={}).status_code == 404
    client.headers["Authorization"] = "Bearer alice"
    with auto.factory.begin() as session:
        item = session.get(Item, source["knowledge_id"])
        item.lifecycle_status = "RETIRED"
    assert client.post(path, json={}).status_code == 409
    with auto.factory() as session:
        assert session.scalar(select(func.count()).select_from(ExtractionRun)) == 0


def test_pending_source_cannot_be_prepared(knowledge_fixture):  # noqa: F811
    client, service, _ = knowledge_fixture
    service.settings.workflow_rdf_enabled = True
    source = client.post("/api/v1/knowledge", json={"title": "대기", "text": TEXT}).json()
    path = f"/api/v1/graph/extraction/knowledge/{source['knowledge_id']}/prepare"
    assert client.post(path, json={}).status_code == 409
    service.settings.workflow_rdf_enabled = False
    assert client.post(path, json={}).status_code == 503


def test_agent_mode_pauses_existing_runs_without_deleting_them(knowledge_fixture):  # noqa: F811
    client, service, auto, source = setup(knowledge_fixture)
    queued = client.post(f"/api/v1/graph/extraction/knowledge/{source['knowledge_id']}").json()
    auto.config = AutoGraphSettings(_env_file=None)
    assert not auto.process_one()
    with auto.factory() as session:
        run = session.get(ExtractionRun, queued["id"])
        assert run.status == "PENDING" and run.attempts == 0
    auto.config = AutoGraphSettings(_env_file=None, mode="service", enabled=True, model="test")
    assert auto.process_one()
