"""Install the shared skill for Codex or Claude; optionally register its MCP server."""

import argparse
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def install(destination: Path, *, overwrite: bool = False) -> None:
    if destination.exists() and not overwrite:
        raise FileExistsError("Destination exists; use --overwrite to update this skill explicitly")
    if destination.is_symlink():
        raise ValueError("Refusing to overwrite a symlink destination")
    shutil.copytree(ROOT / "skills/vector-knowledge", destination, dirs_exist_ok=overwrite)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("agent", choices=["codex", "claude"])
    parser.add_argument("--destination", type=Path, help="Override the personal skill directory")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--register-mcp",
        action="store_true",
        help="Register/update vector_knowledge in this client's user MCP settings",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    destination = args.destination or (
        Path.home() / (".agents" if args.agent == "codex" else ".claude") / "skills/vector-knowledge"
    )
    launcher = str(ROOT / "scripts/run_configured_knowledge_mcp.sh")
    command = (
        ["codex", "mcp", "add", "vector_knowledge", "--", launcher]
        if args.agent == "codex"
        else [
            "claude",
            "mcp",
            "add",
            "--transport",
            "stdio",
            "--scope",
            "user",
            "vector_knowledge",
            "--",
            launcher,
        ]
    )
    print("Skill destination:", destination)
    if args.register_mcp:
        print("MCP command:", command)
    if args.dry_run:
        return
    if args.register_mcp and shutil.which(args.agent) is None:
        raise SystemExit("Install the selected agent CLI before --register-mcp")
    install(destination, overwrite=args.overwrite)
    if args.register_mcp:
        subprocess.run(command, check=True)
    print("Installed. Start a new agent session. Automatic storage requires your authorization.")


if __name__ == "__main__":
    main()
