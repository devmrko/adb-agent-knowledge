from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
from dotenv import dotenv_values

from knowledge_app.graph_auto_contracts import AutoGraphSettings
from knowledge_app.graph_auto_extractor import HTTPExtractor
from scripts import configure_local_graph, prepare_knowledge_rdf


def test_local_profile_preserves_credentials_and_does_not_send_cloud_key(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    profile = Path("config/gemma-local.env").read_text()
    (tmp_path / "config/gemma-local.env").write_text(profile)
    (tmp_path / ".env").write_text('USER_PASSWORD="secret#unchanged"\nOPENROUTER_API_KEY=old-cloud-key\n')
    monkeypatch.setattr(configure_local_graph, "ROOT", tmp_path)
    monkeypatch.setattr("sys.argv", ["configure_local_graph", "--apply"])
    configure_local_graph.main()
    values = dotenv_values(tmp_path / ".env")
    assert values["USER_PASSWORD"] == "secret#unchanged"
    assert values["OPENROUTER_API_KEY"] == "old-cloud-key"
    config = AutoGraphSettings(_env_file=tmp_path / ".env")
    assert config.api_key.get_secret_value() == ""
    assert config.allow_remote is False
    assert config.reasoning_effort == "none"
    assert config.structured_output
    assert config.policy == "review"

    def handle(request):
        import json

        body = json.loads(request.content)
        assert request.url.host == "127.0.0.1"
        assert "authorization" not in request.headers
        assert body["reasoning_effort"] == "none"
        assert "provider" not in body
        assert body["response_format"]["type"] == "json_schema"
        assert body["response_format"]["json_schema"]["schema"]["required"] == ["verdicts"]
        return httpx.Response(
            200, json={"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}]}
        )

    client = httpx.Client(transport=httpx.MockTransport(handle))
    with patch("knowledge_app.llm_http.httpx.Client", return_value=client):
        assert HTTPExtractor(config).complete("synthetic", {}) == "{}"


@pytest.mark.parametrize("count,flow,creates", [(0, 0, True), (4, 1, False)])
def test_rdf_preparation_preserves_existing_network(count, flow, creates):
    engine = MagicMock()
    engine.dialect.name = "oracle"
    engine.connect.return_value.__enter__.return_value.scalar.side_effect = [count, flow]
    with (
        patch.object(prepare_knowledge_rdf, "database", return_value=engine),
        patch.object(prepare_knowledge_rdf.setup_workflow_rdf, "main") as workflow,
        patch.object(prepare_knowledge_rdf.setup_shared_rdf, "main") as shared,
        patch.object(prepare_knowledge_rdf.setup_navigation_rdf, "main") as navigation,
    ):
        prepare_knowledge_rdf.main()
        assert workflow.called is creates
        shared.assert_called_once()
        navigation.assert_called_once()


def test_partial_rdf_is_not_replaced():
    engine = MagicMock()
    engine.dialect.name = "oracle"
    engine.connect.return_value.__enter__.return_value.scalar.side_effect = [4, 0]
    with (
        patch.object(prepare_knowledge_rdf, "database", return_value=engine),
        patch.object(prepare_knowledge_rdf.setup_workflow_rdf, "main") as workflow,
        pytest.raises(SystemExit, match="Partial RDF"),
    ):
        prepare_knowledge_rdf.main()
    workflow.assert_not_called()
