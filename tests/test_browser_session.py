import hashlib
import sqlite3

from fastapi.testclient import TestClient

from knowledge_app.app import create_app
from knowledge_app.browser_session import COOKIE
from knowledge_app.models import Base
from knowledge_app.settings import Settings
from tests.test_knowledge import TestEmbedder, TestVerifier

ORIGIN = "https://notes.example.test"
KEY = "test-notes-key-only-" + "a" * 32


def make_app(tmp_path, **overrides):
    values = dict(
        database_url="sqlite:///" + str(tmp_path / "knowledge.db"),
        web_public_origin=ORIGIN,
        web_api_key_sha256=hashlib.sha256(KEY.encode()).hexdigest(),
        web_session_db=str(tmp_path / "sessions.db"),
        web_actor_issuer="test",
        web_actor_subject="alice",
    )
    values.update(overrides)
    app = create_app(Settings(_env_file=None, **values), embedder=TestEmbedder(), verifier=TestVerifier())
    Base.metadata.create_all(app.state.engine)
    return app


def login(client, key=KEY, origin=ORIGIN):
    return client.post(
        "/knowledge/session", json={"api_key": key}, headers={"Origin": origin, "X-Knowledge-UI": "1"}
    )


def test_session_cookie_rotation_logout_and_restart(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app, base_url=ORIGIN) as c:
        assert c.get("/api/v1/knowledge").status_code == 401
        assert login(c, key="x" * 40).status_code == 401
        assert login(c, origin="https://evil.test").status_code == 403
        response = login(c)
        assert response.status_code == 200
        cookie = response.headers["set-cookie"]
        for flag in ("Secure", "HttpOnly", "SameSite=strict", "Path=/", "Max-Age=604800"):
            assert flag in cookie
        assert KEY not in cookie and KEY not in response.text
        first = c.cookies.get(COOKIE)
        assert c.get("/api/v1/knowledge").status_code == 200
        second = login(c)
        sid = c.cookies.get(COOKIE)
        assert sid != first
        assert c.get("/api/v1/knowledge", headers={"Cookie": f"{COOKIE}={first}"}).status_code == 401
        csrf = second.json()["csrf"]
    # Persistent server-side sessions survive process/app restarts.
    with TestClient(make_app(tmp_path), base_url=ORIGIN) as c:
        c.cookies.set(COOKIE, sid)
        assert c.get("/knowledge/session").json()["csrf"] == csrf
        assert c.delete("/knowledge/session").status_code == 403
        assert (
            c.delete("/knowledge/session", headers={"Origin": ORIGIN, "X-CSRF-TOKEN": csrf}).status_code
            == 200
        )
        assert c.get("/api/v1/knowledge", headers={"Cookie": f"{COOKIE}={sid}"}).status_code == 401


def test_csrf_bearer_precedence_and_owner_isolation(tmp_path):
    with TestClient(make_app(tmp_path), base_url=ORIGIN) as c:
        csrf = login(c).json()["csrf"]
        body = {"title": "private", "text": "Oracle"}
        assert c.post("/api/v1/knowledge", json=body).status_code == 403
        assert (
            c.post(
                "/api/v1/knowledge", json=body, headers={"Origin": "https://evil.test", "X-CSRF-TOKEN": csrf}
            ).status_code
            == 403
        )
        assert (
            c.post(
                "/api/v1/knowledge", json=body, headers={"Origin": ORIGIN, "X-CSRF-TOKEN": "wrong"}
            ).status_code
            == 403
        )
        assert (
            c.post(
                "/api/v1/knowledge", json=body, headers={"Origin": ORIGIN, "X-CSRF-TOKEN": csrf}
            ).status_code
            == 202
        )
        assert len(c.get("/api/v1/knowledge").json()["items"]) == 1
        assert c.get("/api/v1/knowledge", headers={"Authorization": "Bearer bob"}).json()["items"] == []
        assert c.get("/api/v1/knowledge", headers={"Authorization": "Bearer invalid"}).status_code == 401
        assert c.get("/api/v1/knowledge", headers={"Authorization": "Basic invalid"}).status_code == 401
        assert (
            c.post("/api/v1/knowledge", json=body, headers={"Authorization": "Bearer bob"}).status_code == 202
        )
        assert c.get("/knowledge/session", headers={"Host": "evil.test"}).status_code == 403
        assert c.post("/knowledge/local-connection").status_code == 404


def test_expiry_rotation_disabled_and_no_plaintext(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app, base_url=ORIGIN) as c:
        login(c)
        sid = c.cookies.get(COOKIE)
        with sqlite3.connect(tmp_path / "sessions.db") as db:
            row = db.execute("SELECT * FROM browser_sessions").fetchone()
            assert sid not in str(row) and KEY not in str(row)
            db.execute("UPDATE browser_sessions SET expires=0")
        assert c.get("/api/v1/knowledge").status_code == 401
        login(c)
        sid = c.cookies.get(COOKIE)
    with TestClient(make_app(tmp_path, web_api_key_sha256="0" * 64), base_url=ORIGIN) as c:
        c.cookies.set(COOKIE, sid)
        assert c.get("/api/v1/knowledge").status_code == 401
    with TestClient(make_app(tmp_path, web_public_origin=""), base_url=ORIGIN) as c:
        assert c.get("/knowledge/session").status_code == 404
        assert login(c).status_code == 401
        assert c.get("/api/v1/knowledge", headers={"Authorization": "Bearer alice"}).status_code == 200
