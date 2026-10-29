"""Live MCP lifecycle smoke test. Creates one isolated test item and retires it on success."""

import asyncio
import json
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    root = Path(__file__).resolve().parents[1]
    async with (
        stdio_client(StdioServerParameters(command=str(root / "scripts/run_knowledge_mcp.sh"))) as (
            read,
            write,
        ),
        ClientSession(read, write, read_timeout_seconds=timedelta(seconds=150)) as session,
    ):
        await session.initialize()
        tools = await session.list_tools()
        assert len(tools.tools) == 12

        async def call(name, args):
            result = await session.call_tool(name, args)
            assert not result.isError, result.content
            return result.structuredContent or json.loads(result.content[0].text)

        async def ready(job_id):
            for _ in range(90):
                job = await call("knowledge_job_status", dict(job_id=job_id))
                if job["status"] == "READY":
                    return
                assert job["status"] != "FAILED", job
                await asyncio.sleep(2)
            raise AssertionError("Indexing timed out")

        request = dict(
            title="[개발 검증] 메모리 변경 이력",
            text="개발 검증용 결정: Oracle 지식 저장소 조회 결과는 최대 3개를 사용한다.",
            memory_kind="DECISION",
            scope="project:memory-validation",
            idempotency_key="memory-smoke-" + str(uuid4()),
        )
        saved = await call("knowledge_save", request)
        repeated = await call("knowledge_save", request)
        assert repeated["knowledge_id"] == saved["knowledge_id"]
        await ready(saved["job_id"])
        found = await call(
            "knowledge_search",
            dict(
                query="Oracle 지식 저장소 조회 결과 개수",
                scopes=[request["scope"]],
                memory_kinds=["DECISION"],
            ),
        )
        assert any(i["knowledge_id"] == saved["knowledge_id"] for i in found["items"])
        new = await call(
            "knowledge_revise",
            dict(
                knowledge_id=saved["knowledge_id"],
                expected_revision_id=saved["revision_id"],
                text="개발 검증용 수정된 결정: Oracle 지식 저장소 조회 결과는 최대 5개를 사용한다.",
                change_note="3개에서 5개로 수정",
            ),
        )
        await ready(new["job_id"])
        history = await call("knowledge_history", dict(knowledge_id=saved["knowledge_id"]))
        assert len(history["revisions"]) == 2
        original = await call(
            "knowledge_get_content",
            dict(knowledge_id=saved["knowledge_id"], revision_id=saved["revision_id"]),
        )
        assert "3개" in original["text"]
        card = await call(
            "knowledge_context",
            dict(query="Oracle 지식 저장소 조회 결과 개수", scopes=[request["scope"]], max_chars=500),
        )
        assert any(e["revision_id"] == new["revision_id"] and "5개" in e["text"] for e in card["entries"])
        await call(
            "knowledge_retire", dict(knowledge_id=saved["knowledge_id"], reason="검증용 기억 비활성화")
        )
        found = await call("knowledge_search", dict(query="Oracle 지식 저장소", scopes=[request["scope"]]))
        assert all(i["knowledge_id"] != saved["knowledge_id"] for i in found["items"])
        await call("knowledge_restore", dict(knowledge_id=saved["knowledge_id"], reason="복원 기능 검증"))
        await call("knowledge_retire", dict(knowledge_id=saved["knowledge_id"], reason="검증 완료"))
        print(
            "PASS 12 MCP tools: scoped save/dedup/search/revise/source/context/retire/restore/history",
            flush=True,
        )
        print("Retired test item:", saved["knowledge_id"], flush=True)


if __name__ == "__main__":
    asyncio.run(main())
