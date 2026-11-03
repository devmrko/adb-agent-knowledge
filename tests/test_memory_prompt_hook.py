import asyncio
import json
import subprocess
import sys
from types import SimpleNamespace

from scripts.install_memory_hook import configure
from scripts.memory_prompt_hook import collect, query_text, scopes_for


class Session:
    def __init__(self, decision="lookup", fail=False):
        self.calls = []
        self.decision, self.fail = decision, fail

    async def call_tool(self, name, args):
        self.calls.append((name, args))
        result = {
            "knowledge_decide": {
                "action": self.decision,
                "user_principles": {
                    "status": "READY",
                    "version": 2,
                    "rules": [{"id": "formal", "instruction": "존댓말을 사용한다"}],
                },
            },
            "knowledge_recall": {"items": [{"knowledge_id": "k1", "revision_id": "r1", "title": "title"}]},
            "knowledge_get_content": {"text": "exact source", "next_offset": None},
        }[name]
        return SimpleNamespace(isError=self.fail, structuredContent=result)


def test_routing_and_exact_content():
    session = Session()
    event = {"prompt": "프로젝트 배포 방법", "cwd": "/work/project"}
    result, calls = asyncio.run(collect(session, event, {"scope_roots": {"/work/project": "project:test"}}))
    assert calls == ["knowledge_decide", "knowledge_recall", "knowledge_get_content"]
    assert result["sources"][0]["text"] == "exact source"
    assert session.calls[1][1]["request"]["scopes"] == ["global", "project:test"]
    assert scopes_for("/work/project-other", {"scope_roots": {"/work/project": "project:test"}}) == ["global"]


def test_skip_and_explicit_override_and_sensitive():
    for prompt, expected in [("안녕", 1), ("이전 배포 기록", 3), ("password=do-not-send", 1)]:
        session = Session("skip")
        result, calls = asyncio.run(collect(session, {"prompt": prompt, "cwd": "/work"}, {}))
        assert len(calls) == expected
        if "password" in prompt:
            assert "do-not-send" not in json.dumps(session.calls)
            assert result["sensitive_prompt_withheld"]
    assert len(query_text("a" * 5000)[0]) == 4000


def test_merge_uninstall_preserve_other_hooks(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(
        json.dumps(
            {
                "other": "keep",
                "hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": "existing"}]}]},
            }
        )
    )
    command = "/python /repo/scripts/memory_prompt_hook.py"
    configure(p, command)
    configure(p, command)
    data = json.loads(p.read_text())
    assert data["other"] == "keep"
    assert len(data["hooks"]["UserPromptSubmit"]) == 2
    configure(p, command, remove=True)
    assert json.loads(p.read_text())["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"] == "existing"


def test_invalid_input_and_dead_mcp_block_without_secret_leak(tmp_path):
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps({"mcp_command": ["/nonexistent/private-secret"], "audit_dir": str(tmp_path)})
    )
    for payload in [
        "{",
        json.dumps({"hook_event_name": "UserPromptSubmit", "prompt": "hello", "cwd": "/work"}),
    ]:
        result = subprocess.run(
            [sys.executable, "scripts/memory_prompt_hook.py", "--config", str(config)],
            input=payload,
            text=True,
            capture_output=True,
            timeout=15,
        )
        assert json.loads(result.stdout)["decision"] == "block"
        assert "private-secret" not in result.stdout + result.stderr
    audit = (tmp_path / "prompt-hook.jsonl").read_text()
    assert "hello" not in audit


def test_timeout_blocks(tmp_path):
    launcher = tmp_path / "hang.py"
    launcher.write_text("import time; time.sleep(30)")
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {"mcp_command": [sys.executable, str(launcher)], "timeout_seconds": 1, "audit_dir": str(tmp_path)}
        )
    )
    result = subprocess.run(
        [sys.executable, "scripts/memory_prompt_hook.py", "--config", str(config)],
        input=json.dumps({"hook_event_name": "UserPromptSubmit", "prompt": "hello", "cwd": "/work"}),
        text=True,
        capture_output=True,
        timeout=8,
    )
    assert json.loads(result.stdout)["decision"] == "block"


def test_explicit_related_scopes_and_validation():
    import pytest

    config = {
        "scope_roots": {
            "/work": ["project:legacy", "project:public", "project:legacy"],
            "/work/independent": "project:other",
        }
    }
    assert scopes_for("/work/child", config) == ["global", "project:legacy", "project:public"]
    assert scopes_for("/work/independent", config) == ["global", "project:other"]
    assert scopes_for("/elsewhere", config) == ["global"]
    for value in [[], [None], ["global"], ["project:"], ["project:has space"], ["project:x"] * 11]:
        with pytest.raises(ValueError):
            scopes_for("/work", {"scope_roots": {"/work": value}})
