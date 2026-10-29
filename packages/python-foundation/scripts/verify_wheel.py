"""Install the wheel into a fresh environment, without source-tree imports."""

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def run(command, **kwargs):
    subprocess.run(command, check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uv", default=str(ROOT / "uvw"))
    args = parser.parse_args()
    wheel = next((ROOT / "dist").glob("devmrko_python_foundation-*.whl"))
    with tempfile.TemporaryDirectory(prefix="foundation-wheel-") as temporary:
        base = Path(temporary)
        environment = base / "venv"
        run([args.uv, "venv", "--python", sys.executable, str(environment)])
        python = environment / "bin/python"
        run([args.uv, "pip", "install", "--python", str(python), str(wheel)])
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        for database in ("sqlite", "oracle"):
            for mode in ("session", "token", "mixed"):
                destination = base / f"app-{database}-{mode}"
                run(
                    [
                        str(environment / "bin/foundation-new"),
                        str(destination),
                        "--package",
                        "consumer",
                        "--database",
                        database,
                        "--auth",
                        mode,
                    ],
                    cwd=base,
                    env=env,
                )
                env.update(
                    FOUNDATION_DATABASE_URL="sqlite:///" + str(destination / "consumer.db"),
                    FOUNDATION_AUTH_MODE=mode,
                    FOUNDATION_ENVIRONMENT="development",
                    FOUNDATION_ISSUER="https://issuer.example",
                    FOUNDATION_AUDIENCE="api",
                    FOUNDATION_JWKS_URL="https://issuer.example/keys",
                    FOUNDATION_DEVELOPMENT_PASSWORD="test-only-generated-password",
                )
                code = """
import pathlib, sys
import python_foundation
assert pathlib.Path(python_foundation.__file__).is_relative_to(pathlib.Path(sys.prefix))
sys.path.insert(0, str(pathlib.Path("src").resolve()))
from consumer.app import create_app, Settings
from python_foundation.security import Actor
from fastapi.testclient import TestClient
class Verifier:
    def verify(self, token):
        from python_foundation.errors import AuthenticationRequired
        if token != "valid": raise AuthenticationRequired()
        return Actor("https://issuer.example", "consumer", frozenset())
settings = Settings()
with TestClient(create_app(settings, verifier=Verifier())) as client:
    assert client.get("/actuator/health").status_code == 200
    assert client.get("/api/ping").status_code == 401
    if settings.auth_mode == "session":
        csrf = client.get("/login").json()["csrf"]
        response = client.post("/login", data={"username":"user", "password":"test-only-generated-password", "csrf":csrf})
        assert response.status_code == 200
    else:
        client.headers["Authorization"] = "Bearer valid"
    assert client.get("/api/ping").json()["status"] == "ok"
"""
                run([str(python), "-c", code], cwd=destination, env=env)
                print(f"PASS installed wheel + generated {database}/{mode} (SQLite runtime)", flush=True)


if __name__ == "__main__":
    main()
