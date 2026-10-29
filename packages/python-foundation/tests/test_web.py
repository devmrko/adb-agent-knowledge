import re

from conftest import PASSWORD, login
from fastapi.testclient import TestClient
from project_contract import verify_project_contract

from python_foundation.security import Actor


def test_java_compatible_project_crud_contract(authenticated):
    verify_project_contract(authenticated)


def test_authentication_csrf_and_safe_validation(client):
    assert client.get("/api/v1/projects").status_code == 401
    response = client.get("/projects", headers={"Accept": "text/html"}, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"].endswith("/login")
    login(client)
    client.headers.pop("X-CSRF-TOKEN")
    assert client.post("/api/v1/projects", json={"name": "blocked"}).status_code == 403
    invalid = client.post("/login", data={"username": "user", "password": PASSWORD, "csrf": "bad"})
    assert invalid.status_code == 403


def test_session_rotation_expiry_and_logout(client, application):
    csrf = login(client)
    old_cookie = client.cookies["foundation_session"]
    assert application.state.security.store.get(old_cookie).actor.subject == "user"
    response = client.post("/logout", data={"csrf": csrf}, follow_redirects=False)
    assert response.status_code == 303
    assert application.state.security.store.get(old_cookie) is None
    client.cookies.set("foundation_session", old_cookie)
    assert client.get("/api/v1/projects").status_code == 401


def test_feature_permissions_are_enforced_at_service_boundary(application, client):
    import pytest

    from example_app.models import CreateProject
    from python_foundation.errors import AccessDenied

    viewer = Actor("local", "viewer", frozenset())
    with pytest.raises(AccessDenied):
        application.state.projects.create(CreateProject(name="direct call"), viewer)
    key, record = application.state.security.store.create(viewer, 60)
    client.cookies.set("foundation_session", key)
    client.headers["X-CSRF-TOKEN"] = record.csrf
    assert client.get("/api/v1/projects").status_code == 200
    assert client.post("/api/v1/projects", json={"name": "denied"}).status_code == 403
    assert client.put("/api/v1/projects/missing", json={"name": "denied", "version": 0}).status_code == 403
    assert client.delete("/api/v1/projects/missing").status_code == 403


def test_html_escapes_names_and_form_validation(authenticated):
    response = authenticated.post("/api/v1/projects", json={"name": "<script>alert(1)</script>"})
    assert response.status_code == 201
    page = authenticated.get("/projects")
    assert "&lt;script&gt;" in page.text
    assert "<script>alert(1)</script>" not in page.text
    csrf = re.search(r'name="_csrf" content="([^"]+)"', page.text).group(1)
    assert authenticated.post("/projects", data={"name": " ", "csrf": csrf}).status_code == 400


def test_unknown_errors_are_sanitized_and_request_id_is_server_generated(application):
    @application.get("/test-crash")
    def crash():
        raise RuntimeError("secret-token-and-SQL")

    with TestClient(application) as client:
        response = client.get("/test-crash", headers={"X-Request-ID": "untrusted"})
    assert response.status_code == 500
    assert "secret" not in response.text
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert response.headers["x-request-id"] == response.json()["requestId"]
    assert response.headers["x-request-id"] != "untrusted"


def test_openapi_is_authenticated_and_records_typed_contract(authenticated, client):
    schema = authenticated.get("/openapi.json")
    assert schema.status_code == 200
    assert "/api/v1/projects/{project_id}" in schema.json()["paths"]
    assert "RenameProject" in schema.json()["components"]["schemas"]


def test_location_honors_root_path(application):
    with TestClient(application, root_path="/foundation") as client:
        login(client)
        response = client.post("/api/v1/projects", json={"name": "Context"})
        assert response.headers["location"].startswith("http://testserver/foundation/api/v1/projects/")


def test_request_size_limit_and_http_protocol_headers(authenticated):
    response = authenticated.post(
        "/api/v1/projects", content=b"x" * 1_100_000, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 413
    response = authenticated.patch("/actuator/health")
    assert response.status_code == 405
    assert "GET" in response.headers["allow"]
