import re
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from example_app.app import create_app
from python_foundation.settings import FoundationSettings

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "test-only-password-very-long"


@pytest.fixture
def settings(tmp_path, monkeypatch):
    database_url = "sqlite:///" + str(tmp_path / "test.db")
    monkeypatch.setenv("FOUNDATION_DATABASE_URL", database_url)
    monkeypatch.setenv("FOUNDATION_DEVELOPMENT_PASSWORD", PASSWORD)
    monkeypatch.setenv("FOUNDATION_AUTH_MODE", "session")
    command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
    return FoundationSettings(database_url=database_url, development_password=PASSWORD)


@pytest.fixture
def application(settings):
    return create_app(settings)


@pytest.fixture
def client(application):
    with TestClient(application) as client:
        yield client


def login(client):
    page = client.get("/login")
    csrf = re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)
    original = client.cookies["foundation_session"]
    response = client.post(
        "/login", data={"username": "user", "password": PASSWORD, "csrf": csrf}, follow_redirects=False
    )
    assert response.status_code == 303, response.text
    assert client.cookies["foundation_session"] != original
    page = client.get("/projects")
    csrf = re.search(r'name="_csrf" content="([^"]+)"', page.text).group(1)
    client.headers["X-CSRF-TOKEN"] = csrf
    return csrf


@pytest.fixture
def authenticated(client):
    login(client)
    return client
