import asyncio
import json
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError
from test_knowledge import knowledge as knowledge_fixture  # noqa: F401

from knowledge_app import rdf
from knowledge_app.routing import MemoryDecision, MemoryRouter, RoutingSettings
from knowledge_app.workflow import WorkflowInput

FLOW = {
    "verified": True,
    "nodes": [{"id": "a", "label": "접수"}, {"id": "b", "label": "검토"}],
    "edges": [{"source": "a", "target": "b", "relation": "next", "evidence": "접수 후 검토"}],
}


def test_grounding_and_invalid_graph():
    assert WorkflowInput.model_validate(FLOW).grounded("접수 후 검토")
    assert not WorkflowInput.model_validate(FLOW).grounded("검토 후 접수")
    bad = {**FLOW, "edges": [{**FLOW["edges"][0], "target": "missing"}]}
    with pytest.raises(ValidationError):
        WorkflowInput.model_validate(bad)
    with pytest.raises(ValidationError):
        WorkflowInput.model_validate({**FLOW, "verified": False})


def test_workflow_revision_isolation_and_idempotency(knowledge_fixture):  # noqa: F811
    client, service, _ = knowledge_fixture
    service.settings.workflow_rdf_enabled = True
    first = client.post("/api/v1/knowledge", json={"title": "절차", "text": "접수 후 검토"}).json()
    assert service.process_one()
    root = "/api/v1/knowledge/" + first["knowledge_id"]
    path = root + "/revisions/" + first["revision_id"] + "/workflow"
    assert client.get(path).json()["status"] == "ABSENT"
    assert client.put(path, json=FLOW).json()["status"] == "READY"
    assert client.put(path, json=FLOW).json()["status"] == "READY"
    assert client.get(path).json()["edges"][0]["relation"] == "next"
    changed = {**FLOW, "edges": [{**FLOW["edges"][0], "relation": "depends_on"}]}
    assert client.put(path, json=changed).status_code == 409
    client.headers["Authorization"] = "Bearer bob"
    assert client.get(path).status_code == 404
    assert client.put(path, json=FLOW).status_code == 404
    client.headers["Authorization"] = "Bearer alice"
    second = client.post(
        root + "/revisions", json={"expected_revision_id": first["revision_id"], "text": "검토 후 접수"}
    ).json()
    assert client.put(path, json=FLOW).status_code == 409
    assert service.process_one()
    assert client.get(path).json()["status"] == "INACTIVE"
    latest = root + "/revisions/" + second["revision_id"] + "/workflow"
    assert client.get(latest).json()["status"] == "ABSENT"
    assert client.put(latest, json=FLOW).status_code == 400
    client.post(root + "/retire", json={"reason": "폐기"})
    assert client.get(latest).json()["status"] == "INACTIVE"


def test_native_rdf_serialization_roundtrip():
    flow = WorkflowInput.model_validate(FLOW)
    owner, revision = "0" * 64, str(uuid4())
    rows = rdf.rows(owner, revision, flow)

    class FakeResult:
        def all(self):
            return rows

    class FakeSession:
        def execute(self, statement, parameters):
            assert parameters["g"] == f"VK_FLOW:<{rdf.graph(owner, revision)}>"
            assert "GET_MODEL" in str(statement)
            return FakeResult()

    assert rdf.read(FakeSession(), owner, revision).digest() == flow.digest()


@pytest.mark.parametrize(
    "operation,score,action",
    [
        ("graph_lookup", 0.5, "graph_lookup"),
        ("graph_lookup", 0.3, "agent_review"),
        ("graph_extract", 0.8, "graph_extract"),
        ("graph_extract", 0.1, "skip"),
    ],
)
def test_graph_routing(operation, score, action):
    def handler(request):
        key = next(iter(json.loads(request.content)["questions"]))
        return httpx.Response(200, json={"answers": {key: {"type": "noul", "noul": score}}})

    router = MemoryRouter(RoutingSettings(_env_file=None), transport=httpx.MockTransport(handler))
    result = asyncio.run(
        router.decide(MemoryDecision(operation=operation, text="접수 후 검토", verified=True))
    )
    assert result["action"] == action
    opt_out = asyncio.run(
        router.decide(
            MemoryDecision(
                operation="graph_extract", text="접수 후 검토", explicit_request=True, storage_allowed=False
            )
        )
    )
    assert opt_out["action"] == "skip"
