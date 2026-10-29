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
