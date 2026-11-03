"""Bounded, read-only dialogue context for context-aware query routing."""

import json
import os
import re
from pathlib import Path

MAX_TAIL = 256 * 1024


def message_text(row):
    """Supported transcript shapes only; never stringify arbitrary content."""
    if row.get("type") == "response_item":
        msg = row.get("payload", {})
        if msg.get("type") != "message":
            return None
    elif row.get("type") in {"user", "assistant"}:
        msg = row.get("message", {})
    else:
        return None
    if not isinstance(msg, dict):
        return None
    role = msg.get("role")
    if role not in {"user", "assistant"}:
        return None
    if role == "assistant" and msg.get("channel") not in {None, "final"}:
        return None
    content = msg.get("content")
    if isinstance(content, str):
        return role, content
    if not isinstance(content, list):
        return None
    # Tool results, tool calls and reasoning mixed into a message are not context.
    if any(
        not isinstance(c, dict) or c.get("type") not in {"text", "input_text", "output_text"} for c in content
    ):
        return None
    return role, "\n".join(c.get("text", "") for c in content if isinstance(c.get("text"), str))


def followup_context(event, config, secret):
    if config.get("followup_context", True) is False:
        return "", "disabled", 0
    session = event.get("session_id")
    raw_path = event.get("transcript_path")
    if (
        not isinstance(session, str)
        or not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", session)
        or not isinstance(raw_path, str)
    ):
        return "", "unavailable", 0
    roots = config.get(
        "transcript_roots",
        [
            str(Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "sessions"),
            str(Path.home() / ".claude/projects"),
        ],
    )
    try:
        path = Path(raw_path).resolve(strict=True)
        if (
            session not in path.stem
            or not path.is_file()
            or not any(path.is_relative_to(Path(r).expanduser().resolve()) for r in roots)
        ):
            return "", "unavailable", 0
        with path.open("rb") as stream:
            size = stream.seek(0, 2)
            stream.seek(max(0, size - MAX_TAIL))
            lines = stream.read(MAX_TAIL).splitlines()
        if size > MAX_TAIL:
            lines = lines[1:]
    except (OSError, ValueError, TypeError):
        return "", "unavailable", 0
    messages = []
    for line in lines:
        try:
            row = json.loads(line)
            if not isinstance(row, dict):
                continue
            if row.get("sessionId", session) != session:
                continue
            item = message_text(row)
            if item and item[1].strip() and item not in messages[-1:]:
                messages.append(item)
        except (ValueError, TypeError):
            continue
    excerpts = []
    for role, text in reversed(messages[-6:]):
        if text.strip() == event["prompt"].strip():
            continue
        if secret.search(text) or any(
            marker in text
            for marker in (
                "<environment_context>",
                "<INSTRUCTIONS>",
                "Memory check completed",
                "<send_user_message",
                "# AGENTS.md",
            )
        ):
            break
        excerpts.append(f"{role}: {text.strip()[:560]}")
        if len(excerpts) == 2:
            break
    if not excerpts:
        return "", "unavailable", 0
    return "\n".join(reversed(excerpts))[:1200], "used", len(excerpts)
