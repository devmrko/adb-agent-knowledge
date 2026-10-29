import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from dotenv import dotenv_values

from scripts import install_agent
from scripts.configure_knowledge import initialize
from scripts.install_agent import install

ROOT = Path(__file__).resolve().parents[1]


def test_setup_preserves_config_and_generates_token(tmp_path):
    (tmp_path / ".env.example").write_text("USER_NAME=\nDEV_API_TOKEN=\n")
    assert initialize(tmp_path)
    token = dotenv_values(tmp_path / ".env")["DEV_API_TOKEN"]
    assert len(token) >= 24
    assert (tmp_path / ".env").stat().st_mode & 0o777 == 0o600
    assert not initialize(tmp_path)
    assert dotenv_values(tmp_path / ".env")["DEV_API_TOKEN"] == token


def test_skill_install_is_portable_and_no_overwrite(tmp_path):
    destination = tmp_path / "custom skills/vector-knowledge"
    install(destination)
    assert (destination / "SKILL.md").is_file()
    assert "name: adb-agent-knowledge" in (destination / "SKILL.md").read_text()
    assert not list(destination.rglob(".env"))
    with pytest.raises(FileExistsError):
        install(destination)
    install(destination, overwrite=True)


def test_supervisor_migrates_and_stops_services(tmp_path):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    env = dict(
        os.environ,
        DATABASE_URL="sqlite:///" + str(tmp_path / "portable.db"),
        DEV_API_TOKEN="portable-test-token-not-a-secret",
        API_PORT=str(port),
        API_HOST="127.0.0.1",
        ENVIRONMENT="development",
        EMBEDDING_REVISION="a" * 40,
    )
    process = subprocess.Popen(
        [sys.executable, "-m", "knowledge_app.launcher", "--migrate"],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        with httpx.Client(trust_env=False, timeout=0.5) as client:
            for _ in range(80):
                assert process.poll() is None, process.communicate()[0].decode()
                try:
                    if client.get(f"http://127.0.0.1:{port}/actuator/health").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.1)
            else:
                raise AssertionError("Portable API did not start")
        process.send_signal(signal.SIGINT)
        output, _ = process.communicate(timeout=20)
        assert process.returncode == 0, output.decode()
        with socket.socket() as listener:
            assert listener.connect_ex(("127.0.0.1", port)) != 0
    finally:
        if process.poll() is None:
            process.terminate()
            process.communicate(timeout=20)


@pytest.mark.parametrize("agent", ["codex", "claude"])
@pytest.mark.parametrize("name", [None, "personal_knowledge", "work-memory", "vector_knowledge"])
def test_installer_registers_selected_name_and_skill(tmp_path, monkeypatch, agent, name):
    destination = tmp_path / "skill"
    argv = ["install_agent", agent, "--destination", str(destination), "--register-mcp"]
    if name is not None:
        argv += ["--mcp-name", name]
    calls = []
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(install_agent.shutil, "which", lambda _: "/fake/client")
    monkeypatch.setattr(install_agent.subprocess, "run", lambda args, **kw: calls.append((args, kw)))
    install_agent.main()
    expected = name or "adb_agent_knowledge"
    launcher = str(ROOT / "scripts/run_configured_knowledge_mcp.sh")
    prefix = [agent, "mcp", "add"]
    if agent == "claude":
        prefix += ["--transport", "stdio", "--scope", "user"]
    assert calls == [(prefix + [expected, "--", launcher], {"check": True})]
    assert f"This installation targets `{expected}`" in (destination / "SKILL.md").read_text()


@pytest.mark.parametrize("name", ["", "-bad", "two words", "bad/name", "x;echo", "한글", "a" * 65])
def test_installer_rejects_invalid_name_before_mutation(tmp_path, monkeypatch, name):
    destination = tmp_path / "skill"
    monkeypatch.setattr(
        sys,
        "argv",
        ["install_agent", "codex", "--destination", str(destination), "--register-mcp", "--mcp-name=" + name],
    )
    monkeypatch.setattr(
        install_agent.subprocess, "run", lambda *a, **kw: pytest.fail("registered invalid name")
    )
    with pytest.raises(SystemExit) as error:
        install_agent.main()
    assert error.value.code == 2
    assert not destination.exists()


def test_installer_dry_run_has_no_side_effects(tmp_path, monkeypatch, capsys):
    destination = tmp_path / "skill"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "install_agent",
            "claude",
            "--destination",
            str(destination),
            "--register-mcp",
            "--mcp-name",
            "preview_memory",
            "--dry-run",
        ],
    )
    monkeypatch.setattr(
        install_agent.subprocess, "run", lambda *a, **kw: pytest.fail("dry-run registered MCP")
    )
    install_agent.main()
    assert not destination.exists()
    assert "preview_memory" in capsys.readouterr().out


def test_skill_update_replaces_selected_registration(tmp_path):
    destination = tmp_path / "skill"
    install(destination, server_name="first_memory")
    install(destination, overwrite=True, server_name="second_memory")
    text = (destination / "SKILL.md").read_text()
    assert text.count("## Selected MCP registration") == 1
    assert "This installation targets `second_memory`" in text
    assert "first_memory" not in text
