"""Queue current source revisions chronologically through the authenticated API; never replay history."""

import argparse
import asyncio
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Any
from zoneinfo import ZoneInfo

from knowledge_app.mcp_server import KnowledgeAPI, configured_api


async def pages(api: KnowledgeAPI, path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = await api.request("GET", path, params={"offset": offset, "limit": 100})
        rows.extend(page["items"])
        if "next_offset" in page:
            if page["next_offset"] is None:
                return rows
            offset = page["next_offset"]
        elif len(page["items"]) < 100:
            return rows
        else:
            offset += 100


def timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


async def snapshot(api: KnowledgeAPI) -> list[dict[str, Any]]:
    items = await pages(api, "/api/v1/knowledge")
    semaphore = asyncio.Semaphore(4)

    async def inspect(item: dict[str, Any]) -> dict[str, Any] | None:
        if not item.get("revision_id") or item["status"] != "READY":
            return None
        async with semaphore:
            history = await api.request("GET", f"/api/v1/knowledge/{item['knowledge_id']}/history")
        active = next((r for r in history["revisions"] if r["active"]), None)
        if not active or active["revision_id"] != item["revision_id"]:
            return None
        return {
            "knowledge_id": item["knowledge_id"],
            "revision_id": active["revision_id"],
            "saved_at": timestamp(active["created_at"]).isoformat(),
            "day": timestamp(active["created_at"]).astimezone(ZoneInfo("Asia/Seoul")).date().isoformat(),
        }

    rows = await asyncio.gather(*(inspect(item) for item in items))
    return sorted((r for r in rows if r), key=lambda r: (r["saved_at"], r["revision_id"]))


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    dates: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        dates[row["day"]][row.get("status", "PLANNED")] += 1
    return {"total": len(rows), "by_saved_date_kst": {d: dict(v) for d, v in sorted(dates.items())}}


async def run(args: argparse.Namespace) -> None:
    api = configured_api()
    schema = await api.request("GET", "/api/v1/graph/extraction/schema")
    if args.apply and (not schema["enabled"] or schema["policy"] != "review"):
        raise SystemExit("This candidate batch requires enabled extraction with policy=review")
    rows = await snapshot(api)
    report = {
        "started_at": datetime.now(UTC).isoformat(),
        "schema": schema["version"],
        "model": schema["model"],
        "policy": schema["policy"],
        "scope": "authenticated user's active revisions only; not historical replay",
        "items": rows,
    }

    def write() -> None:
        report["summary"] = summarize(rows)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.report.with_suffix(".tmp")
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        temporary.chmod(0o600)
        temporary.replace(args.report)

    write()
    print(json.dumps(report["summary"], ensure_ascii=False), flush=True)
    if not args.apply:
        return
    for index, row in enumerate(rows, 1):
        result = await api.request("POST", f"/api/v1/graph/extraction/knowledge/{row['knowledge_id']}")
        row.update(
            run_id=result["id"],
            status=result["status"] if result["revision_id"] == row["revision_id"] else "SOURCE_CHANGED",
        )
        write()
        if index % 25 == 0:
            print(f"Queued/reused {index}/{len(rows)}", flush=True)
    deadline = monotonic() + args.watch_seconds
    while True:
        runs = {r["id"]: r for r in await pages(api, "/api/v1/graph/extraction/runs")}
        for row in rows:
            if row["status"] == "SOURCE_CHANGED":
                continue
            result = runs.get(row["run_id"])
            if result:
                row.update(
                    status=result["status"], error_code=result["error_code"], attempts=result["attempts"]
                )
        pending = sum(r["status"] in {"PENDING", "RUNNING"} for r in rows)
        report["pending"] = pending
        report["updated_at"] = datetime.now(UTC).isoformat()
        write()
        print(json.dumps({"pending": pending, **report["summary"]}, ensure_ascii=False), flush=True)
        if not pending or monotonic() >= deadline:
            return
        await asyncio.sleep(15)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--watch-seconds", type=int, default=0)
    parser.add_argument("--report", type=Path, default=Path(".run/graph-batch-by-date.json"))
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
