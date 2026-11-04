import asyncio
import json
import subprocess
import sys
from types import SimpleNamespace

from scripts.install_memory_hook import configure
from scripts.memory_prompt_hook import collect, query_text, scopes_for


class Session:
    def __init__(self, decision="lookup", fail=False, context_used=False, unresolved=False):
        self.context_used, self.unresolved = context_used, unresolved
        self.calls = []
        self.decision, self.fail = decision, fail

    async def call_tool(self, name, args):
        self.calls.append((name, args))
        result = {
            "knowledge_decide": {
                "action": self.decision,
                "retrieval_query": None
                if self.unresolved
                else args.get("text", "") + ("\n" + args.get("context", "") if self.context_used else ""),
                "context_used": self.context_used,
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
    assert session.calls[1][1]["request"]["graph_mode"] == "auto"
    assert result["graph_expansion"] == "auto"
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


def transcript(tmp_path, rows):
    path = tmp_path / "session-12345678.jsonl"
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows))
    return {"prompt": "남은건?", "cwd": "/work", "session_id": "12345678", "transcript_path": str(path)}, {
        "transcript_roots": [str(tmp_path)]
    }


def test_followup_uses_resolved_session_context(tmp_path):
    event, config = transcript(
        tmp_path,
        [
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "v3 신규 Oracle 스키마 설치 검증해줘"}],
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "channel": "analysis",
                    "content": [{"type": "output_text", "text": "DO_NOT_SEND_THINKING"}],
                },
            },
            {
                "type": "response_item",
                "payload": {"type": "function_call_output", "output": "DO_NOT_SEND_TOOL"},
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "channel": "final",
                    "content": [{"type": "output_text", "text": "v3 전환 완료. 새 설치 검증이 남았습니다."}],
                },
            },
        ],
    )
    session = Session("lookup", context_used=True)
    result, calls = asyncio.run(collect(session, event, config))
    assert len(calls) == 3
    assert result["decision"] == "lookup"
    assert result["followup_context"] == {"status": "used", "messages": 2}
    query = session.calls[1][1]["request"]["text"]
    assert "신규 Oracle" in query and "남은건?" in query
    assert "DO_NOT_SEND" not in json.dumps(session.calls)


def test_claude_followup_and_secret_boundary(tmp_path):
    event, config = transcript(
        tmp_path,
        [
            {
                "type": "user",
                "sessionId": "12345678",
                "message": {"role": "user", "content": "v3 Oracle 설치 검증"},
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "다음은 이력 검증입니다."}],
                },
            },
        ],
    )
    session = Session()
    result, _ = asyncio.run(collect(session, event, config))
    assert result["followup_context"]["status"] == "used"
    path = __import__("pathlib").Path(event["transcript_path"])
    with path.open("a") as f:
        f.write(
            "\n" + json.dumps({"type": "user", "message": {"role": "user", "content": "password=PRIVATE"}})
        )
    session = Session("agent_review", unresolved=True)
    result, calls = asyncio.run(collect(session, event, config))
    assert len(calls) == 1 and result["decision"] == "agent_review"
    assert "PRIVATE" not in json.dumps(session.calls)


def test_missing_wrong_session_root_and_disabled_context(tmp_path):
    event, config = transcript(
        tmp_path, [{"type": "user", "message": {"role": "user", "content": "v3 Oracle 새 스키마"}}]
    )
    variants = [
        ({**event, "session_id": "87654321"}, config),
        (event, {"transcript_roots": ["/different"]}),
        (event, {**config, "followup_context": False}),
        ({"prompt": "남은건?", "cwd": "/work"}, config),
    ]
    for e, c in variants:
        session = Session("agent_review", unresolved=True)
        result, calls = asyncio.run(collect(session, e, c))
        assert len(calls) == 1 and result["decision"] == "agent_review"
        assert result["user_principles"]["version"] == 2


def test_independent_prompt_never_inherits_previous_topic(tmp_path):
    event, config = transcript(
        tmp_path, [{"type": "user", "message": {"role": "user", "content": "v3 Oracle 새 스키마"}}]
    )
    event["prompt"] = "HTTP 404와 410의 차이"
    session = Session()
    result, _ = asyncio.run(collect(session, event, config))
    assert result["followup_context"]["status"] == "used"
    assert session.calls[1][1]["request"]["text"] == event["prompt"]
