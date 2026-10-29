import time

import jwt
import pytest
from conftest import login
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from pydantic import ValidationError

from example_app.app import create_app
from python_foundation.errors import AuthenticationRequired
from python_foundation.security import JwtTokenVerifier, MemorySessionStore, Security
from python_foundation.settings import FoundationSettings


@pytest.fixture(scope="module")
def private_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def token(key, **overrides):
    claims = {
        "iss": "https://issuer.example",
        "aud": "projects-api",
        "sub": "alice",
        "exp": int(time.time()) + 300,
        "scope": "project:write",
    }
    claims.update(overrides)
    return jwt.encode(claims, key, algorithm="RS256", headers={"typ": "at+jwt"})


def token_settings(settings, mode):
    return FoundationSettings(
        **{
            **settings.model_dump(),
            "auth_mode": mode,
            "issuer": "https://issuer.example",
            "audience": "projects-api",
            "jwks_url": "https://issuer.example/keys",
        }
    )


@pytest.mark.parametrize("mode", ["token", "mixed"])
def test_bearer_mode_and_session_isolation(settings, private_key, mode):
    config = token_settings(settings, mode)
    verifier = JwtTokenVerifier(config, key_provider=lambda value: private_key.public_key())
    app = create_app(config, verifier=verifier)
    with TestClient(app) as client:
        if mode == "mixed":
            login(client)
            assert client.get("/projects").status_code == 200
        assert client.get("/api/v1/projects").status_code == 401
        client.headers["Authorization"] = "Basic dXNlcjpwYXNzd29yZA=="
        assert client.get("/api/v1/projects").status_code == 401
        client.headers["Authorization"] = "Bearer invalid"
        assert client.get("/api/v1/projects").status_code == 401
        client.headers["Authorization"] = "Bearer " + token(private_key)
        response = client.post("/api/v1/projects", json={"name": "Token"})
        assert response.status_code == 201
        if mode == "token":
            assert not client.cookies
            assert client.get("/login").status_code == 404


def test_mixed_token_boundary_with_root_path(settings, private_key):
    config = token_settings(settings, "mixed")
    app = create_app(
        config, verifier=JwtTokenVerifier(config, key_provider=lambda value: private_key.public_key())
    )
    with TestClient(app, root_path="/foundation") as client:
        login(client)
        assert client.get("/api/v1/projects").status_code == 401
        client.headers["Authorization"] = "Bearer " + token(private_key)
        assert client.get("/api/v1/projects").status_code == 200


@pytest.mark.parametrize(
    "claims",
    [
        {"iss": "https://wrong.example"},
        {"aud": "other"},
        {"exp": int(time.time()) - 300},
        {"nbf": int(time.time()) + 300},
        {"sub": ""},
        {"scope": ["admin"]},
    ],
)
def test_invalid_claims_are_rejected(settings, private_key, claims):
    config = token_settings(settings, "token")
    verifier = JwtTokenVerifier(config, key_provider=lambda value: private_key.public_key())
    with pytest.raises(AuthenticationRequired):
        verifier.verify(token(private_key, **claims))


def test_wrong_signature_type_and_missing_expiry(settings, private_key):
    config = token_settings(settings, "token")
    verifier = JwtTokenVerifier(config, key_provider=lambda value: private_key.public_key())
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    claims = {"iss": config.issuer, "aud": config.audience, "sub": "alice", "exp": int(time.time()) + 300}
    invalid = [
        token(other),
        jwt.encode(claims, private_key, algorithm="RS256", headers={"typ": "JWT"}),
        jwt.encode(
            {k: v for k, v in claims.items() if k != "exp"},
            private_key,
            algorithm="RS256",
            headers={"typ": "at+jwt"},
        ),
        jwt.encode(
            claims, "not-a-real-secret-that-is-long-enough", algorithm="HS256", headers={"typ": "at+jwt"}
        ),
    ]
    for value in invalid:
        with pytest.raises(AuthenticationRequired):
            verifier.verify(value)


def test_settings_and_session_expiry():
    with pytest.raises(ValidationError):
        FoundationSettings(auth_mode="token")
    with pytest.raises(ValidationError):
        FoundationSettings(pool_size=0)
    with pytest.raises(ValidationError):
        FoundationSettings(environment="production", cookie_secure=False)
    with pytest.raises(ValueError, match="shared SessionStore"):
        Security(FoundationSettings(environment="production", cookie_secure=True))
    now = [0.0]
    store = MemorySessionStore(clock=lambda: now[0])
    key, _ = store.create(None, ttl=60)
    assert store.get(key) is not None
    now[0] = 61
    assert store.get(key) is None
