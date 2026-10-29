"""Preview/apply portable Codex/Claude memory policy without uploading local knowledge."""

import argparse
import hashlib
import json
import os
import re
import stat
import tempfile
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
BEGIN = "<!-- BEGIN vector-knowledge-global-policy -->"
END = "<!-- END vector-knowledge-global-policy -->"
PROJECT_BEGIN = "<!-- BEGIN vector-knowledge-memory-policy -->"
PROJECT_END = "<!-- END vector-knowledge-memory-policy -->"
INSTRUCTIONS = {"AGENTS.md", "AGENTS.override.md", "CLAUDE.md", "CLAUDE.local.md"}
EXCLUDE = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    ".cache",
    "Library",
    "Applications",
    ".Trash",
    ".npm",
    ".rustup",
    ".cargo",
    ".gradle",
    "target",
    "build",
    "dist",
    "site-packages",
    "plugins",
    "tool-results",
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_path(path: Path) -> Path:
    path = Path(os.path.abspath(path.expanduser()))
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError(f"Symlink path refused: {path}")
    return path


def merge_block(original: str, block: str, begin: str, end: str) -> str:
    if begin in original or end in original:
        if (
            original.count(begin) != 1
            or original.count(end) != 1
            or original.index(begin) > original.index(end)
        ):
            raise ValueError("Invalid managed policy markers; repair them before applying")
        return original[: original.index(begin)] + block + original[original.index(end) + len(end) :]
    return original + ("\n\n" if original else "") + block + "\n"


def inventory(roots: list[Path]) -> tuple[list[Path], list[Path], list[str]]:
    instructions, memories, errors = set(), set(), []
    for root in roots:
        root = safe_path(root)
        if not root.is_dir():
            raise ValueError(f"Search root is not a directory: {root}")
        for directory, dirs, files in os.walk(root, onerror=lambda e: errors.append(str(e.filename))):
            dirs[:] = sorted(d for d in dirs if d not in EXCLUDE and not Path(directory, d).is_symlink())
            for name in files:
                path = Path(directory, name)
                if path.is_symlink():
                    continue
                if name in INSTRUCTIONS:
                    instructions.add(path)
                elif name in {"MEMORY.md", "memory_summary.md"} or (
                    name.endswith(".md")
                    and {"memory", "memories"}.intersection(path.parts)
                    and {".codex", ".claude"}.intersection(path.parts)
                ):
                    memories.add(path)
    return sorted(instructions), sorted(memories), sorted(set(errors))


def plan(home: Path, roots: list[Path], allow_auto_save: bool, disable_claude: bool) -> dict:
    home = safe_path(home)
    instructions, memories, errors = inventory(roots)
    capture = (
        "The user authorizes selective automatic capture of confirmed preferences, decisions, stable project facts and verified outcomes."
        if allow_auto_save
        else "Save on explicit request. Selective automatic capture requires the current user's separate standing authorization; installation alone grants none."
    )
    policy = (
        (ROOT / "config/agent-memory/global.md").read_text().replace("{{CAPTURE_POLICY}}", capture).strip()
    )
    global_block = BEGIN + "\n" + policy + "\n" + END
    project_block = (ROOT / "config/agent-memory/project.md").read_text().strip()
    targets = {p: (project_block, PROJECT_BEGIN, PROJECT_END) for p in instructions}
    for p in [home / ".codex/AGENTS.md", home / ".claude/CLAUDE.md"]:
        targets[p] = (global_block, BEGIN, END)
    changes, warnings = [], []
    for path, (block, begin, end) in sorted(targets.items()):
        safe_path(path)
        old = path.read_bytes() if path.exists() else None
        original = old.decode("utf-8") if old is not None else ""
        updated = merge_block(original, block, begin, end).encode()
        if old != updated:
            changes.append({"path": path, "before": old, "after": updated})
        outside = re.sub(
            r"<!-- BEGIN vector-knowledge-.*?<!-- END vector-knowledge-.*?-->", "", original, flags=re.S
        )
        if re.search(r"knowledge_decide|knowledge_search|Personal knowledge|자동.*메모리", outside):
            warnings.append(f"Review existing memory instructions outside managed block: {path}")
    if disable_claude:
        path = safe_path(home / ".claude/settings.json")
        old = path.read_bytes() if path.exists() else None
        settings = json.loads(old) if old is not None else {}
        if not isinstance(settings, dict):
            raise ValueError("Claude settings must be a JSON object")
        if settings.get("autoMemoryEnabled") is not False:
            settings["autoMemoryEnabled"] = False
            changes.append(
                {
                    "path": path,
                    "before": old,
                    "after": (json.dumps(settings, ensure_ascii=False, indent=2) + "\n").encode(),
                }
            )
    return {"changes": changes, "memories": memories, "unreadable": errors, "warnings": warnings}


def replace(path: Path, data: bytes, mode: int) -> None:
    safe_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".vk-policy-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        os.chmod(name, mode)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def apply(changes: list[dict], home: Path) -> Path | None:
    if not changes:
        return None
    for change in changes:
        path = safe_path(change["path"])
        if (path.read_bytes() if path.exists() else None) != change["before"]:
            raise ValueError(f"File changed since planning: {path}")
    directory = safe_path(home / ".local/state/vector-knowledge/policy-backups" / str(uuid4()))
    directory.mkdir(parents=True, mode=0o700)
    entries = []
    for number, change in enumerate(changes):
        path, old = change["path"], change["before"]
        mode = stat.S_IMODE(path.stat().st_mode) if old is not None else 0o600
        backup = f"{number}.bak" if old is not None else None
        if backup:
            replace(directory / backup, old, 0o600)
        entries.append(
            {
                "path": str(path),
                "backup": backup,
                "before_sha256": digest(old) if old is not None else None,
                "after_sha256": digest(change["after"]),
                "mode": mode,
            }
        )
    manifest = directory / "manifest.json"
    replace(manifest, (json.dumps({"version": 1, "files": entries}, indent=2) + "\n").encode(), 0o600)
    for change, entry in zip(changes, entries, strict=True):
        replace(change["path"], change["after"], entry["mode"])
    return manifest


def restore(manifest: Path, write: bool) -> int:
    manifest = safe_path(manifest)
    records = json.loads(manifest.read_text())["files"]
    pending = []
    for record in records:
        path = safe_path(Path(record["path"]))
        current = path.read_bytes() if path.exists() else None
        current_hash = digest(current) if current is not None else None
        if current_hash == record["before_sha256"]:
            continue
        if current_hash != record["after_sha256"]:
            raise ValueError(f"File changed after application; refusing restore: {path}")
        original = None
        if record["backup"]:
            name = record["backup"]
            if Path(name).name != name:
                raise ValueError("Invalid backup filename")
            original = safe_path(manifest.parent / name).read_bytes()
            if digest(original) != record["before_sha256"]:
                raise ValueError("Backup checksum mismatch")
        pending.append((path, original, record["mode"]))
    if write:
        for path, original, mode in pending:
            if original is None:
                path.unlink()
            else:
                replace(path, original, mode)
    return len(pending)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--home", type=Path, default=Path.home(), help="Agent home; defaults to this user's home"
    )
    parser.add_argument(
        "--root", type=Path, action="append", help="Scan root; repeat for multiple folders; default: home"
    )
    parser.add_argument("--apply", action="store_true", help="Write changes (default: preview only)")
    parser.add_argument(
        "--allow-auto-save", action="store_true", help="Explicitly authorize selective MCP memory capture"
    )
    parser.add_argument(
        "--disable-claude-auto-memory",
        action="store_true",
        help="Disable Claude's separate automatic local memory",
    )
    parser.add_argument(
        "--restore", type=Path, help="Preview restoring a trusted local backup manifest; --apply restores"
    )
    args = parser.parse_args()
    try:
        if args.restore:
            print(json.dumps({"restore_files": restore(args.restore, args.apply), "applied": args.apply}))
            return
        home = safe_path(args.home)
        result = plan(home, args.root or [home], args.allow_auto_save, args.disable_claude_auto_memory)
        manifest = apply(result["changes"], home) if args.apply else None
        print(
            json.dumps(
                {
                    "applied": args.apply,
                    "changed_files": [str(c["path"]) for c in result["changes"]],
                    "memory_files_for_manual_migration": [str(p) for p in result["memories"]],
                    "unreadable": result["unreadable"],
                    "warnings": result["warnings"],
                    "backup_manifest": str(manifest) if manifest else None,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    except (ValueError, OSError) as error:
        parser.exit(1, f"Policy update failed: {error}\n")


if __name__ == "__main__":
    main()
