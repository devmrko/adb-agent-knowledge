"""Actual synthetic model probes, without DB writes or user knowledge transfer."""

import argparse
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from dotenv import dotenv_values

from knowledge_app.embedding import create_embedder, validate_vectors
from knowledge_app.routing import RoutingSettings
from knowledge_app.settings import ROOT, Settings


def kev_probe(url: str, key: str, model: str) -> dict[str, object]:
    headers = {"Authorization": "Bearer " + key} if key else {}
    with httpx.Client(trust_env=False, timeout=60, follow_redirects=False) as client:
        response = client.post(
            url.rstrip("/") + "/v1/systemone",
            headers=headers,
            json={
                "state": "Find my saved installation notes.",
                "model": model,
                "questions": {
                    "need_lookup": {"type": "noul", "instructions": "Would recalling saved knowledge help?"}
                },
            },
        )
        response.raise_for_status()
        score = response.json()["answers"]["need_lookup"]["noul"]
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= score <= 1:
            raise ValueError("Invalid Kev score")
        return {"score": score}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("component", choices=["embedding", "kev"])
    parser.add_argument(
        "--start-local", action="store_true", help="Start/stop an isolated local Kev process for this check"
    )
    parser.add_argument("--startup-timeout", type=int, default=600)
    args = parser.parse_args()
    os.environ.setdefault("HF_HOME", str(ROOT / ".cache/huggingface"))
    if args.component == "embedding":
        settings = Settings()
        embedder = create_embedder(settings)
        for query in (False, True):
            validate_vectors(embedder.encode(["설치 검증용 가상 지식입니다."], query=query), 1, 1024)
        print(
            f"Embedding inference PASS: {settings.embedding_provider}, {settings.embedding_model}, 1024 dimensions"
        )
        return
    routing = RoutingSettings()
    if not args.start_local:
        kev_probe(routing.url, routing.api_key.get_secret_value(), routing.model)
        print("Configured Kev inference PASS")
        return
    values = dotenv_values(ROOT / ".env")
    repo = Path(
        os.environ.get("KEV_REPO_DIR") or values.get("KEV_REPO_DIR") or ROOT / ".tools/kev"
    ).expanduser()
    if not repo.is_absolute():
        repo = ROOT / repo
    python = repo / ".venv/bin/python"
    if not python.is_file():
        raise ValueError("Local Kev environment missing; run setup_kev.sh or configure KEV_REPO_DIR")
    model = os.environ.get("KEV_RUN") or values.get("KEV_RUN") or "jaredpalmer/kev-4b"
    device = os.environ.get("KEV_DEVICE") or values.get("KEV_DEVICE") or "auto"
    if device not in {"auto", "cpu", "cuda", "mps"}:
        raise ValueError("KEV_DEVICE must be auto/cpu/cuda/mps")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    with tempfile.TemporaryFile() as log:
        child = subprocess.Popen(
            [
                str(python),
                "-m",
                "kev.serve",
                "--run",
                model,
                "--device",
                device,
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=repo,
            stdout=log,
            stderr=log,
        )
        try:
            deadline = time.monotonic() + args.startup_timeout
            while time.monotonic() < deadline:
                if child.poll() is not None:
                    raise ValueError(
                        "Kev startup failed; check supported backend, dependencies, model access and memory"
                    )
                try:
                    with httpx.Client(trust_env=False, timeout=2) as client:
                        result = client.get(f"http://127.0.0.1:{port}/v1/models")
                        if result.status_code == 200:
                            break
                except httpx.HTTPError:
                    pass
                time.sleep(1)
            else:
                raise ValueError("Kev startup timed out; check model download and available memory")
            kev_probe(f"http://127.0.0.1:{port}", "", routing.model)
            print("Isolated local Kev inference PASS; test process will be stopped")
        finally:
            child.terminate()
            try:
                child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Never echo provider response bodies or configured secrets.
        print(
            f"Model verification FAILED ({type(error).__name__}); check endpoint/backend and configuration.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
