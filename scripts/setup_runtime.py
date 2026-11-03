"""One installation entrypoint; never changes database objects or existing configuration."""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def commands(with_models: bool, verify: bool, with_agent_memory: bool = False) -> list[list[str]]:
    python = str(ROOT / ".venv/bin/python")
    result = [
        [str(ROOT / "uvw"), "sync", "--locked", "--python", "3.12", "--extra", "knowledge", "--extra", "mcp"],
        [python, str(ROOT / "scripts/configure_knowledge.py")],
    ]
    if with_agent_memory:
        result[0].extend(["--extra", "agent-memory"])
    if with_models:
        result.append([str(ROOT / "scripts/setup_kev.sh")])
    if verify:
        result.append([python, "-m", "scripts.check_model_runtime", "embedding"])
        result.append(
            [python, "-m", "scripts.check_model_runtime", "kev", *(["--start-local"] if with_models else [])]
        )
    return result


def configured_agent_memory() -> bool:
    # Read only non-secret feature switches before installing dependencies.
    switches = {}
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text().splitlines():
            key, sep, value = line.partition("=")
            key = key.strip().removeprefix("export ").strip().upper()
            if sep and key in {"KNOWLEDGE_SOURCE_BACKEND", "AGENT_MEMORY_ENABLED"}:
                switches[key] = value.split("#", 1)[0].strip().strip("\"'").lower()
    for key in ["KNOWLEDGE_SOURCE_BACKEND", "AGENT_MEMORY_ENABLED"]:
        if key in os.environ:
            switches[key] = os.environ[key].lower()
    return switches.get("KNOWLEDGE_SOURCE_BACKEND") == "v3" or switches.get("AGENT_MEMORY_ENABLED") in {
        "true",
        "1",
        "yes",
    }


def validate_platform(system: str) -> None:
    if system not in {"Darwin", "Linux"}:
        raise ValueError(
            "Native Windows/other OS installers are not supported. On Windows use WSL2 Ubuntu, "
            "install Git and python3-venv there, clone inside WSL, then run scripts/setup.sh."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--with-models", action="store_true", help="Also install the pinned local Kev runtime"
    )
    parser.add_argument(
        "--verify-models",
        action="store_true",
        help="Download/load and query embeddings and Kev; may take minutes",
    )
    parser.add_argument(
        "--plan", action="store_true", help="Print commands without installation or downloads"
    )
    parser.add_argument(
        "--with-agent-memory", action="store_true", help="Install SDK for v3 knowledge or agent memories"
    )
    args = parser.parse_args()
    validate_platform(platform.system())
    if not shutil.which("git"):
        raise ValueError("Git is required. Install Git for this OS, then rerun setup.")
    print(
        f"Installer: {platform.system()} {platform.machine()}; API Python 3.12, Kev Python 3.13", flush=True
    )
    for command in commands(
        args.with_models, args.verify_models, args.with_agent_memory or configured_agent_memory()
    ):
        if args.plan:
            print(" ".join(command))
        else:
            subprocess.run(command, cwd=ROOT, check=True)
    if not args.plan:
        print("Setup complete. Existing .env preserved; fill Wallet/DB credentials before --migrate.")
        print(
            "GPU drivers are not installed by this script. CPU is the embedding default; remote providers are optional."
        )
        if not args.verify_models:
            print(
                "Model inference NOT verified. Use --verify-models to download/load and test configured models."
            )


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"Setup failed: {error}", file=sys.stderr)
        raise SystemExit(1) from None
