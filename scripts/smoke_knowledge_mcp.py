"""Exercise real stdio MCP against the running API/worker. Saves a development note."""

import asyncio
import json
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]


async def main():
    parameters = StdioServerParameters(command=str(ROOT / "scripts/run_knowledge_mcp.sh"))
    async with (
        stdio_client(parameters) as (read, write),
        ClientSession(read, write, read_timeout_seconds=timedelta(seconds=150)) as session,
    ):
        await session.initialize()
        tools = await session.list_tools()
        print("MCP tools:", ",".join(tool.name for tool in tools.tools), flush=True)

        async def call(name, args):
            result = await session.call_tool(name, args)
            assert not result.isError, result.content
            return result.structuredContent or json.loads(result.content[0].text)

        saved = await call(
            "knowledge_save",
            {
                "title": "[개발 검증] Codex 지식 저장소 연결",
                "text": "Codex 지식 저장소는 vector_knowledge MCP를 통해 저장과 검색을 수행한다. Oracle Autonomous Database에 원문과 벡터를 보관하며 로컬 워커가 임베딩한다.",
                "category": "Codex",
                "tags": ["MCP", "지식저장소"],
            },
        )
        print("Saved job:", saved["job_id"], flush=True)
        for _ in range(60):
            job = await call("knowledge_job_status", {"job_id": saved["job_id"]})
            if job["status"] in {"READY", "FAILED"}:
                break
            await asyncio.sleep(2)
        assert job["status"] == "READY", job
        found = await call(
            "knowledge_search", {"query": "Codex에서 저장한 지식은 어디에 보관되나?", "category": "Codex"}
        )
        item = next(i for i in found["items"] if i["knowledge_id"] == saved["knowledge_id"])
        content = await call(
            "knowledge_get_content",
            {"knowledge_id": item["knowledge_id"], "revision_id": item["revision_id"]},
        )
        assert "Oracle Autonomous" in content["text"]
        print("PASS stdio MCP save -> READY -> search -> original content", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
