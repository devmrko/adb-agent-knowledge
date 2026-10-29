"""Start isolated owned Python/optional Java servers and run the shared HTTP contract."""

import argparse
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from check_contract import authenticate, verify_project_contract

ROOT = Path(__file__).resolve().parents[1]


def run_server(command, env, directory, auth):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    arguments = command + (["--port", str(port)] if auth == "form" else [f"--server.port={port}"])
    with open(Path(directory) / (auth + ".log"), "w") as log:
        process = subprocess.Popen(
            arguments,
            cwd=ROOT if auth == "form" else directory,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            with httpx.Client(
                base_url=f"http://127.0.0.1:{port}", timeout=10, follow_redirects=False
            ) as client:
                deadline = time.monotonic() + 60
                while True:
                    if process.poll() is not None:
                        raise RuntimeError(f"{auth} server exited during startup")
                    try:
                        if client.get("/actuator/health").status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    if time.monotonic() > deadline:
                        raise TimeoutError("Application startup timed out")
                    time.sleep(0.2)
                authenticate(client, auth, "user", env["CONTRACT_PASSWORD"])
                verify_project_contract(client)
        finally:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--java-jar", type=Path)
    parser.add_argument("--java", default="java")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="python-foundation-runtime-") as directory:
        env = os.environ.copy()
        env.update(
            FOUNDATION_DATABASE_URL="sqlite:///" + str(Path(directory) / "python.db"),
            FOUNDATION_AUTH_MODE="session",
            FOUNDATION_ENVIRONMENT="development",
            FOUNDATION_DEVELOPMENT_PASSWORD=secrets.token_urlsafe(32),
        )
        env["CONTRACT_PASSWORD"] = env["FOUNDATION_DEVELOPMENT_PASSWORD"]
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, env=env, check=True)
        run_server(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "example_app.app:create_app",
                "--factory",
                "--host",
                "127.0.0.1",
            ],
            env,
            directory,
            "form",
        )
        print("PASS Python process: Alembic migration, login/CSRF, shared CRUD contract", flush=True)
        if args.java_jar:
            env.update(
                DATABASE_URL="jdbc:sqlite:" + str(Path(directory) / "java.db"),
                SPRING_PROFILES_ACTIVE="sqlite",
                SPRING_SECURITY_USER_PASSWORD=secrets.token_urlsafe(32),
            )
            env["CONTRACT_PASSWORD"] = env["SPRING_SECURITY_USER_PASSWORD"]
            run_server([args.java, "-jar", str(args.java_jar.resolve())], env, directory, "basic")
            print("PASS Java process: same shared CRUD contract", flush=True)


if __name__ == "__main__":
    main()
