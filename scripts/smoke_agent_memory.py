"""Exercise the actual MCP -> HTTP -> SDK path against an isolated Oracle account."""

import argparse
import asyncio
import json
import os
import secrets
from pathlib import Path

import httpx
from dotenv import dotenv_values


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--env-file", required=True)
    p.add_argument("--store-id", default="AKMTEST1102")
    p.add_argument("--hf-home", help="Optional Hugging Face model cache directory")
    a = p.parse_args()
    values = dotenv_values(a.env_file)
    if not (
        values.get("USER_NAME", "").startswith("VKV_") or values.get("USER_NAME", "").startswith("OAM_TEST_")
    ):
        raise SystemExit("Use isolated test account")
    for key, value in values.items():
        if value is not None:
            os.environ[key] = value
    os.environ["AGENT_MEMORY_STORE_ID"] = a.store_id
    os.environ["AGENT_MEMORY_ENABLED"] = "true"
    os.environ["EMBEDDING_REVISION"] = "55ec6e9358a56d56af759bc8372e970caf8c305f"
    if a.hf_home:
        os.environ["HF_HOME"] = str(Path(a.hf_home).expanduser().resolve())
    from alembic import command
    from alembic.config import Config

    from knowledge_app.agent_memory_repository import SDKRepository
    from knowledge_app.app import create_app
    from knowledge_app.embedding import create_embedder
    from knowledge_app.mcp_server import KnowledgeAPI, create_server
    from knowledge_app.settings import Settings

    command.upgrade(Config("alembic.ini"), "head")
    token = secrets.token_urlsafe(32)
    settings = Settings(_env_file=None, dev_api_token=token)
    repo = SDKRepository(settings, create_embedder(settings))
    repo.connect(initialize=True)
    repo.close()
    app = create_app(settings)
    api = KnowledgeAPI("http://127.0.0.1:8137", token, transport=httpx.ASGITransport(app=app))
    server = create_server(api)

    async def call(name, args):
        value = await server.call_tool(name, args)
        if isinstance(value, tuple):
            return value[1]
        return json.loads(value[0].text)

    key = secrets.token_hex(6)
    agent = await call(
        "memory_profile_save", {"profile": {"kind": "agent", "key": key, "name": "통합 테스트 도우미"}}
    )
    thread = await call(
        "memory_profile_save",
        {"profile": {"kind": "thread", "key": key, "name": "SDK 연결 검증", "agent_id": agent["id"]}},
    )
    memory = {
        "title": "SDK 통합 검증 기록",
        "text": "이 기록은 MCP를 통해 Oracle 에이전트 메모리 저장과 조회를 검증하기 위한 합성 테스트다.",
        "scope": "project:agent-memory-validation",
        "agent_id": agent["id"],
        "origin_thread_id": thread["id"],
        "idempotency_key": key,
    }
    saved = await call("memory_save", {"memory": memory})
    assert saved["status"] == "READY"
    again = await call("memory_save", {"memory": memory})
    assert again["memory_id"] == saved["memory_id"] and again["reused"]
    rows = await call("memory_search", {"request": {"agent_id": agent["id"]}})
    assert rows["items"][0]["thread_name"] == "SDK 연결 검증"
    search = await call("memory_search", {"request": {"agent_id": agent["id"], "query": "무엇을 검증했나?"}})
    assert saved["memory_id"] in [r["memory_id"] for r in search["items"]]
    renamed = await call(
        "memory_profile_save",
        {"profile": {"kind": "agent", "key": key, "name": "이름 변경 검증", "expected_version": 1}},
    )
    assert renamed["id"] == agent["id"] and renamed["version"] == 2
    note = await call(
        "knowledge_save",
        {
            "title": "SDK 근거 연결 테스트",
            "text": "Oracle 통합 테스트의 실제 근거 문장",
            "scope": "project:agent-memory-validation",
            "idempotency_key": key + "-source",
        },
    )
    assert await asyncio.to_thread(app.state.service.process_one)
    proof = {
        "memory_id": saved["memory_id"],
        "knowledge_id": note["knowledge_id"],
        "revision_id": note["revision_id"],
        "quote": "실제 근거 문장",
        "reason": "합성 테스트의 정확한 인용",
    }
    linked = await call("memory_link_knowledge", {"evidence": proof})
    assert linked["status"] == "CURRENT"
    second = await call(
        "memory_save",
        {
            "memory": {
                **memory,
                "title": "관계 조회 확인",
                "text": "이 합성 테스트는 기억 관계 탐색을 검증한다.",
                "idempotency_key": key + "-second",
            }
        },
    )
    relation = {
        "source_id": second["memory_id"],
        "target_id": saved["memory_id"],
        "relation": "supports",
        "reason": "두 합성 기록의 연결 조회를 검증한다",
    }
    await call("memory_link", {"link": relation})
    assert (await call("memory_link", {"link": relation}))["reused"]
    graph = await call("memory_graph", {"graph": {"memory_id": saved["memory_id"], "depth": 2}})
    assert len(graph["edges"]) == 1 and len(graph["nodes"]) == 2
    changed = await call(
        "knowledge_revise",
        {
            "knowledge_id": note["knowledge_id"],
            "expected_revision_id": note["revision_id"],
            "text": "Oracle 통합 테스트의 변경된 근거",
            "change_note": "근거 현재성 검증",
        },
    )
    assert await asyncio.to_thread(app.state.service.process_one)
    refs = await call("memory_references", {"memory_id": saved["memory_id"]})
    assert refs["items"][0]["status"] == "REVIEW_REQUIRED"
    assert refs["items"][0]["revision_id"] != changed["revision_id"]
    print("MCP_EVIDENCE_REVISION_AND_SDK_RELATION_PASS")
    print("MCP_SDK_SAVE_BROWSE_SEARCH_RENAME_IDEMPOTENCY_PASS")
    app.state.agent_memory.repo.close()
    app.state.engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
