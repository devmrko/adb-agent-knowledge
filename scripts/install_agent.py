"""Install the shared skill for Codex or Claude; optionally register its MCP server."""

import argparse
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MCP_NAME = "adb_agent_knowledge"


def mcp_name(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", value):
        raise argparse.ArgumentTypeError(
            "MCP name must start with an ASCII letter and contain 1–64 letters, digits, _ or -"
        )
    return value


def install(destination: Path, *, overwrite: bool = False, server_name: str = DEFAULT_MCP_NAME) -> None:
    server_name = mcp_name(server_name)
    if destination.exists() and not overwrite:
        raise FileExistsError("Destination exists; use --overwrite to update this skill explicitly")
    if destination.is_symlink():
        raise ValueError("Refusing to overwrite a symlink destination")
    shutil.copytree(ROOT / "skills/vector-knowledge", destination, dirs_exist_ok=overwrite)
    skill = destination / "SKILL.md"
    skill.write_text(
        skill.read_text()
        + "\n## Selected MCP registration\n\n"
        + f"This installation targets `{server_name}`. Use that server's `knowledge_*` tools. "
        + "Client tool prefixes can vary; inspect the connected catalog. If it is missing, "
        + "report the connection problem instead of silently using another knowledge service.\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("agent", choices=["codex", "claude"])
    parser.add_argument("--destination", type=Path, help="Override the personal skill directory")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--mcp-name",
        type=mcp_name,
        default=DEFAULT_MCP_NAME,
        help="Client MCP registration name (default: %(default)s)",
    )
    parser.add_argument(
        "--register-mcp",
        action="store_true",
        help="Register the selected MCP name in this client's user settings",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    destination = args.destination or (
        Path.home() / (".agents" if args.agent == "codex" else ".claude") / "skills/vector-knowledge"
    )
    launcher = str(ROOT / "scripts/run_configured_knowledge_mcp.sh")
    command = (
        ["codex", "mcp", "add", args.mcp_name, "--", launcher]
        if args.agent == "codex"
        else [
            "claude",
            "mcp",
            "add",
            "--transport",
            "stdio",
            "--scope",
            "user",
            args.mcp_name,
            "--",
            launcher,
        ]
    )
    print("Skill destination:", destination)
    print("MCP registration:", args.mcp_name)
    if args.register_mcp:
        print("MCP command:", command)
    if args.dry_run:
        return
    if args.register_mcp and shutil.which(args.agent) is None:
        raise SystemExit("Install the selected agent CLI before --register-mcp")
    install(destination, overwrite=args.overwrite, server_name=args.mcp_name)
    if args.register_mcp:
        subprocess.run(command, check=True)
    print("Installed. Start a new agent session. Automatic storage requires your authorization.")


if __name__ == "__main__":
    main()
