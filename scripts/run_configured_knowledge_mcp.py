"""Use this checkout's explicit SSH configuration, otherwise its local MCP adapter."""

import os
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
values = dotenv_values(ROOT / ".env")
remote = os.environ.get("KNOWLEDGE_SSH_HOST") or values.get("KNOWLEDGE_SSH_HOST")
launcher = ROOT / "scripts" / ("run_remote_knowledge_mcp.sh" if remote else "run_knowledge_mcp.sh")
os.execv(str(launcher), [str(launcher)])
