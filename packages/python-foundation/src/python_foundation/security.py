"""Explicit authentication adapters and per-operation authorization contracts."""

import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, cast

import jwt
from fastapi import Request
from fastapi.responses import Response
from jwt import PyJWKClient

from python_foundation.errors import AccessDenied, AuthenticationRequired
from python_foundation.settings import FoundationSettings


@dataclass(frozen=True)
class Actor:
    issuer: str
    subject: str
    authorities: frozenset[str]

    def __post_init__(self) -> None:
        if not self.issuer.strip() or not self.subject.strip():
            raise ValueError("Actor issuer and subject must not be blank")
        object.__setattr__(self, "authorities", frozenset(self.authorities))

    def require(self, authority: str) -> "Actor":
        if not authority.strip():
            raise ValueError("Authority must not be blank")
        if authority not in self.authorities:
            raise AccessDenied()
        return self


class AuthorizationPolicy(Protocol):
    """Service-owned resource/tenant policy; implementations belong to the consuming app."""

    def authorize(self, actor: Actor, action: str, resource_id: str | None = None) -> None: ...


@dataclass(frozen=True)
class SessionRecord:
    actor: Actor | None
    csrf: str
    expires_at: float


class SessionStore(Protocol):
    """Implement atomically with a shared TTL store for production/multiple processes."""

    def create(self, actor: Actor | None, ttl: int) -> tuple[str, SessionRecord]: ...
    def get(self, session_id: str) -> SessionRecord | None: ...
    def delete(self, session_id: str) -> None: ...


class MemorySessionStore:
    """Bounded development store. A process restart invalidates every session."""

    def __init__(self, capacity: int = 10_000, clock: Callable[[], float] = time.monotonic) -> None:
        if capacity < 1:
            raise ValueError("Session capacity must be positive")
        self._capacity = capacity
        self._clock = clock
        self._records: dict[str, SessionRecord] = {}
        self._lock = threading.Lock()

    def create(self, actor: Actor | None, ttl: int) -> tuple[str, SessionRecord]:
        with self._lock:
            now = self._clock()
            self._records = {key: value for key, value in self._records.items() if value.expires_at > now}
            if len(self._records) >= self._capacity:
                from python_foundation.errors import BusinessError, ErrorCategory, ErrorSpec

                raise BusinessError(
                    ErrorSpec(
                        "SESSION_CAPACITY", ErrorCategory.UNAVAILABLE, "Login is temporarily unavailable."
                    )
                )
            key = secrets.token_urlsafe(32)
            record = SessionRecord(actor, secrets.token_urlsafe(32), now + ttl)
            self._records[key] = record
            return key, record

    def get(self, session_id: str) -> SessionRecord | None:
        with self._lock:
            record = self._records.get(session_id)
            if record is not None and record.expires_at <= self._clock():
                self._records.pop(session_id, None)
                return None
            return record

    def delete(self, session_id: str) -> None:
        with self._lock:
            self._records.pop(session_id, None)


class TokenVerifier(Protocol):
    def verify(self, token: str) -> Actor: ...


class JwtTokenVerifier:
    """RS256 access-token validation; never trusts algorithms or role claims from a token."""

    def __init__(
        self, settings: FoundationSettings, key_provider: Callable[[str], Any] | None = None
    ) -> None:
        if not settings.issuer or not settings.audience or not settings.jwks_url:
            raise ValueError("JWT verifier requires issuer, audience and JWKS URL")
        self._issuer = settings.issuer
        self._audience = settings.audience
        client = PyJWKClient(settings.jwks_url, timeout=settings.http_timeout_seconds)
        self._key_provider = key_provider or (lambda token: client.get_signing_key_from_jwt(token).key)

    def verify(self, token: str) -> Actor:
        try:
            if len(token) > 8192:
                raise AuthenticationRequired()
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256" or str(header.get("typ", "")).lower() not in {
                "at+jwt",
                "application/at+jwt",
            }:
                raise AuthenticationRequired()
            claims = jwt.decode(
                token,
                self._key_provider(token),
                algorithms=["RS256"],
                issuer=self._issuer,
                audience=self._audience,
                leeway=60,
                options={"require": ["exp", "iss", "aud", "sub"]},
            )
            subject = claims["sub"]
            scope = claims.get("scope", "")
            if not isinstance(subject, str) or not subject.strip() or not isinstance(scope, str):
                raise AuthenticationRequired()
            return Actor(self._issuer, subject, frozenset("SCOPE_" + item for item in scope.split()))
        except jwt.PyJWTError as failure:
            raise AuthenticationRequired() from failure


class Security:
    """Select authentication by route; route functions select feature authorities."""

    cookie_name = "foundation_session"

    def __init__(
        self,
        settings: FoundationSettings,
        *,
        store: SessionStore | None = None,
        verifier: TokenVerifier | None = None,
    ) -> None:
        self.settings = settings
        if settings.environment == "production" and settings.auth_mode != "token":
            if store is None or isinstance(store, MemorySessionStore):
                raise ValueError(
                    "Production session authentication requires a shared SessionStore implementation"
                )
        self.store = store or MemorySessionStore()
        self.verifier = verifier
        if settings.auth_mode in {"token", "mixed"} and verifier is None:
            self.verifier = JwtTokenVerifier(settings)

    def token_route(self, path: str) -> bool:
        return self.settings.auth_mode == "token" or (
            self.settings.auth_mode == "mixed" and (path == "/api" or path.startswith("/api/"))
        )

    @staticmethod
    def path(request: Request) -> str:
        path = str(request.scope["path"])
        root = str(request.scope.get("root_path", "")).rstrip("/")
        if root and (path == root or path.startswith(root + "/")):
            path = path[len(root) :] or "/"
        return path

    def authenticate(self, request: Request) -> Actor:
        if self.token_route(self.path(request)):
            scheme, _, token = request.headers.get("Authorization", "").partition(" ")
            if scheme.lower() != "bearer" or not token or self.verifier is None:
                raise AuthenticationRequired()
            actor = self.verifier.verify(token)
        else:
            record = self.store.get(request.cookies.get(self.cookie_name, ""))
            if record is None or record.actor is None:
                raise AuthenticationRequired()
            actor = record.actor
        request.state.actor = actor
        return actor

    def api_actor(self, request: Request) -> Actor:
        actor = self.authenticate(request)
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            self.check_csrf(request, request.headers.get("X-CSRF-TOKEN"))
        return actor

    def check_csrf(self, request: Request, token: str | None) -> None:
        if self.token_route(self.path(request)):
            return
        record = self.store.get(request.cookies.get(self.cookie_name, ""))
        if record is None or not token or not secrets.compare_digest(record.csrf, token):
            raise AccessDenied()

    def begin_login(self, request: Request, response: Response) -> str:
        """Creates/reuses anonymous state. Authenticated GETs never log the user out."""
        record = self.store.get(request.cookies.get(self.cookie_name, ""))
        if record is not None:
            return record.csrf
        key, record = self.store.create(None, self.settings.session_ttl_seconds)
        self._cookie(response, key)
        return record.csrf

    def login(self, request: Request, response: Response, actor: Actor, csrf: str) -> str:
        self.check_csrf(request, csrf)
        self.store.delete(request.cookies.get(self.cookie_name, ""))
        key, record = self.store.create(actor, self.settings.session_ttl_seconds)
        self._cookie(response, key)
        return record.csrf

    def logout(self, request: Request, response: Response, csrf: str) -> None:
        self.check_csrf(request, csrf)
        self.store.delete(request.cookies.get(self.cookie_name, ""))
        response.delete_cookie(
            self.cookie_name, path="/", secure=self.settings.cookie_secure, httponly=True, samesite="lax"
        )

    def csrf(self, request: Request) -> str:
        record = self.store.get(request.cookies.get(self.cookie_name, ""))
        if record is None:
            raise AuthenticationRequired()
        return record.csrf

    def _cookie(self, response: Response, key: str) -> None:
        response.set_cookie(
            self.cookie_name,
            key,
            max_age=self.settings.session_ttl_seconds,
            secure=self.settings.cookie_secure,
            httponly=True,
            samesite="lax",
            path="/",
        )


def current_actor(request: Request) -> Actor:
    """Function dependency alternative to controller inheritance."""
    return cast(Security, request.app.state.security).api_actor(request)
