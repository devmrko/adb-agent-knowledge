"""Install/remove the synchronous memory hook without replacing other hooks or trusting it."""

import argparse
import json
import shlex
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKER = "scripts/memory_prompt_hook.py"


def configure(path, command, remove=False, *, on_failure=False):
    original = path.read_text() if path.exists() else None
    doc = json.loads(original) if original else {}
    events = doc.setdefault("hooks", {}).setdefault("UserPromptSubmit", [])
    retained = []
    for group in events:
        handlers = [h for h in group.get("hooks", []) if MARKER not in h.get("command", "")]
        if handlers:
            retained.append({**group, "hooks": handlers})
    if not remove:
        handler = {"type": "command", "command": command, "timeout": 55}
        if on_failure:
            handler["onFailure"] = "block"
        retained.append({"hooks": [handler]})
    doc["hooks"]["UserPromptSubmit"] = retained
    path.parent.mkdir(parents=True, exist_ok=True)
    if original is not None:
        shutil.copy2(path, path.with_name(path.name + ".memory-hook-" + str(time.time_ns()) + ".bak"))
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("agent", choices=["codex", "claude"])
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--settings", type=Path)
    parser.add_argument("--remove", action="store_true")
    args = parser.parse_args()
    config = args.config.expanduser().resolve()
    if not args.remove:
        json.loads(config.read_text())
    command = shlex.join([sys.executable, str(ROOT / MARKER), "--config", str(config)])
    command += " || { printf '%s\n' 'Memory hook failed to start.' >&2; exit 2; }"
    path = args.settings or Path.home() / (
        ".codex/hooks.json" if args.agent == "codex" else ".claude/settings.json"
    )
    configure(path, command, args.remove, on_failure=args.agent == "claude")
    print(("Removed" if args.remove else "Installed") + ": " + str(path))
    if args.agent == "codex" and not args.remove:
        print(
            "Required: review and trust this exact new hook in Codex /hooks. Trust hashes were NOT modified."
        )
    elif not args.remove:
        print("Restart Claude Code and verify an actual prompt hook event.")


if __name__ == "__main__":
    main()
