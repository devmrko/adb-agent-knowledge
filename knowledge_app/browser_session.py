"""Explicit browser-key exchange; raw API keys never persist in browser sessions."""

import hashlib
import secrets
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, SecretStr

from knowledge_app.settings import Settings
from python_foundation.errors import AccessDenied, AuthenticationRequired
from python_foundation.security import Actor

COOKIE = "__Host-vk_session"


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class Login(BaseModel):
    api_key: SecretStr = Field(min_length=24, max_length=512)


class BrowserSessions:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.origin = settings.web_public_origin.rstrip("/")
        parsed = urlsplit(self.origin)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("WEB_PUBLIC_ORIGIN must be an HTTPS origin")
        self.key_hash = settings.web_api_key_sha256.lower()
        if len(self.key_hash) != 64 or any(c not in "0123456789abcdef" for c in self.key_hash):
            raise ValueError("WEB_API_KEY_SHA256 must contain a SHA-256 digest")
        self.actor = Actor(settings.web_actor_issuer, settings.web_actor_subject, frozenset())
        self.binding = digest(self.key_hash + "\0" + self.actor.issuer + "\0" + self.actor.subject)
        self.path = Path(settings.web_session_db).expanduser()
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        # Create with restrictive permissions before SQLite opens it.
        if not self.path.exists():
            import os

            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                pass
            else:
                os.close(fd)
        self.path.chmod(0o600)
        with self.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS browser_sessions "
                "(id TEXT PRIMARY KEY, csrf TEXT NOT NULL, binding TEXT NOT NULL, expires REAL NOT NULL)"
            )

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=5)
        try:
            with db:
                yield db
        finally:
            db.close()

    def check_host(self, request: Request) -> None:
        if f"{request.url.scheme}://{request.url.netloc}" != self.origin:
            raise AccessDenied()

    def check_origin(self, request: Request) -> None:
        self.check_host(request)
        if request.headers.get("origin") != self.origin:
            raise AccessDenied()
        if request.headers.get("sec-fetch-site", "same-origin") != "same-origin":
            raise AccessDenied()

    def record(self, request: Request) -> tuple[str, float]:
        self.check_host(request)
        sid = request.cookies.get(COOKIE, "")
        if not sid or len(sid) > 128:
            raise AuthenticationRequired()
        with self.connect() as db:
            row = db.execute(
                "SELECT csrf, expires FROM browser_sessions WHERE id=? AND binding=? AND expires>?",
                (digest(sid), self.binding, time.time()),
            ).fetchone()
        if row is None:
            raise AuthenticationRequired()
        return str(row[0]), float(row[1])

    def csrf(self, request: Request) -> str:
        csrf, _ = self.record(request)
        self.check_origin(request)
        supplied = request.headers.get("x-csrf-token", "")
        if not secrets.compare_digest(csrf, supplied):
            raise AccessDenied()
        return csrf

    def authenticate(self, request: Request) -> Actor:
        self.record(request)
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            self.csrf(request)
        return self.actor

    def login(self, request: Request, key: str) -> JSONResponse:
        self.check_origin(request)
        if request.headers.get("x-knowledge-ui") != "1":
            raise AccessDenied()
        if not secrets.compare_digest(digest(key), self.key_hash):
            raise AuthenticationRequired()
        sid, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        now = time.time()
        with self.connect() as db:
            db.execute("DELETE FROM browser_sessions WHERE expires<=? OR binding<>?", (now, self.binding))
            db.execute("DELETE FROM browser_sessions WHERE id=?", (digest(request.cookies.get(COOKIE, "")),))
            # Bounded session growth, including multiple legitimate key holders.
            if db.execute("SELECT count(*) FROM browser_sessions").fetchone()[0] >= 10000:
                raise AccessDenied()
            db.execute(
                "INSERT INTO browser_sessions VALUES (?,?,?,?)",
                (digest(sid), csrf, self.binding, now + self.settings.web_session_ttl_seconds),
            )
        response = JSONResponse({"authenticated": True, "csrf": csrf}, headers={"Cache-Control": "no-store"})
        response.set_cookie(
            COOKIE,
            sid,
            max_age=self.settings.web_session_ttl_seconds,
            secure=True,
            httponly=True,
            samesite="strict",
            path="/",
        )
        return response

    def logout(self, request: Request) -> JSONResponse:
        self.csrf(request)
        with self.connect() as db:
            db.execute("DELETE FROM browser_sessions WHERE id=?", (digest(request.cookies.get(COOKIE, "")),))
        response = JSONResponse({"authenticated": False}, headers={"Cache-Control": "no-store"})
        response.delete_cookie(COOKIE, secure=True, httponly=True, samesite="strict", path="/")
        return response


def install_browser_sessions(app: FastAPI, settings: Settings) -> None:
    browser = BrowserSessions(settings) if settings.web_public_origin else None
    app.state.browser_sessions = browser

    @app.get("/knowledge/session", include_in_schema=False)
    def session(request: Request) -> JSONResponse:
        if browser is None:
            return JSONResponse({"enabled": False}, status_code=404)
        csrf, _ = browser.record(request)
        return JSONResponse({"authenticated": True, "csrf": csrf}, headers={"Cache-Control": "no-store"})

    @app.post("/knowledge/session", include_in_schema=False)
    def login(command: Login, request: Request) -> JSONResponse:
        if browser is None:
            raise AuthenticationRequired()
        return browser.login(request, command.api_key.get_secret_value())

    @app.delete("/knowledge/session", include_in_schema=False)
    def logout(request: Request) -> JSONResponse:
        if browser is None:
            raise AuthenticationRequired()
        return browser.logout(request)
