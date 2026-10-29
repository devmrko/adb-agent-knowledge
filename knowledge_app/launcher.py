"""Foreground API/worker supervisor; Ctrl-C terminates managed child processes."""

import argparse
import os
import signal
import subprocess
import sys
import time

from knowledge_app.database import database
from knowledge_app.settings import ROOT, Settings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--migrate", action="store_true", help="Apply additive database migrations before startup"
    )
    parser.add_argument(
        "--kev", action="store_true", help="Start separately installed local Kev alongside API/worker"
    )
    args = parser.parse_args()
    settings = Settings()
    engine = database(settings)
    engine.dispose()
    if args.migrate:
        subprocess.run(
            [sys.executable, "-m", "alembic", "-c", str(ROOT / "alembic.ini"), "upgrade", "head"],
            cwd=ROOT,
            check=True,
        )
    children: list[subprocess.Popen[bytes]] = []
    stopping = False

    def stop(signum: int, frame: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    env = os.environ.copy()
    env.setdefault("HF_HOME", str(ROOT / ".cache/huggingface"))
    commands = [
        [
            sys.executable,
            "-m",
            "uvicorn",
            "knowledge_app.app:create_app",
            "--factory",
            "--host",
            settings.api_host,
            "--port",
            str(settings.api_port),
        ],
        [sys.executable, "-m", "knowledge_app.worker"],
        [sys.executable, "-m", "knowledge_app.graph_auto_worker"],
    ]
    if args.kev:
        commands.insert(0, [str(ROOT / "scripts/run_kev.sh")])
    exit_code = 0
    try:
        for command in commands:
            children.append(subprocess.Popen(command, cwd=ROOT, env=env, start_new_session=True))
        print(f"API: http://{settings.api_host}:{settings.api_port}/docs — Ctrl-C to stop", flush=True)
        while not stopping:
            if any(child.poll() is not None for child in children):
                exit_code = 1
                print("A service stopped; stopping managed services.", file=sys.stderr)
                break
            time.sleep(0.25)
    finally:
        for child in children:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
        for child in children:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
