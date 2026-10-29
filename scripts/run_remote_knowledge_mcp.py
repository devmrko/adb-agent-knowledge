"""Run the remote MCP over SSH, preserving the calling machine's configured provenance."""

import os
import re
import shlex
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
values = dotenv_values(ROOT / ".env")
host = os.environ.get("KNOWLEDGE_SSH_HOST") or values.get("KNOWLEDGE_SSH_HOST") or ""
remote = os.environ.get("KNOWLEDGE_REMOTE_DIR") or values.get("KNOWLEDGE_REMOTE_DIR") or ""
if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._@:-]*", host) or not remote.startswith("/"):
    raise SystemExit("Set a valid SSH host alias and absolute remote directory")
command = ["env"]
for key in ("KNOWLEDGE_MACHINE_ID", "KNOWLEDGE_MACHINE_LABEL"):
    command.append(key + "=" + (os.environ.get(key) or values.get(key) or ""))
command.append(remote + "/scripts/run_knowledge_mcp.sh")
os.execvp("ssh", ["ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host, shlex.join(command)])
