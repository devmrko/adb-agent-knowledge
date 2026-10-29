"""Populate missing derived summaries and reference RDF for the API user's active notes."""

import asyncio

from knowledge_app.mcp_server import configured_api


async def main() -> None:
    api = configured_api()
    offset = count = 0
    while True:
        page = await api.request("GET", "/api/v1/knowledge", params={"offset": offset, "limit": 100})
        for item in page["items"]:
            if item.get("revision_id"):
                await api.request("POST", f"/api/v1/knowledge/{item['knowledge_id']}/refresh-derived")
                count += 1
        if len(page["items"]) < 100:
            break
        offset += 100
    print(f"Refreshed {count} active notes; source revisions preserved")


if __name__ == "__main__":
    asyncio.run(main())
