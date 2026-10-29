"""Copy one explicitly selected legacy workflow into the shared graph without merging names."""

import argparse
import asyncio
from uuid import UUID

from knowledge_app.mcp_server import configured_api


async def migrate(knowledge_id: UUID, revision_id: UUID) -> None:
    api = configured_api()
    root = f"/api/v1/knowledge/{knowledge_id}"
    item = await api.request("GET", root)
    flow = await api.request("GET", f"{root}/revisions/{revision_id}/workflow")
    if flow["status"] != "READY":
        raise SystemExit("The selected legacy workflow must be active and READY")
    source = await api.request("GET", f"{root}/revisions/{revision_id}/content")
    if any(edge["evidence"] not in source["text"] for edge in flow["edges"]):
        raise SystemExit("Source evidence mismatch; no changes made")
    scope = item["scope"]
    nodes = {}
    for node in flow["nodes"]:
        entity = await api.request(
            "POST",
            "/api/v1/graph/entities",
            json={
                "identity_key": f"legacy:{knowledge_id}:{node['id']}",
                "label": node["label"],
                "scope": scope,
            },
        )
        nodes[node["id"]] = entity["id"]
    for edge in flow["edges"]:
        await api.request(
            "POST",
            "/api/v1/graph/assertions",
            json={
                "scope": scope,
                "subject_id": nodes[edge["source"]],
                "predicate": edge["relation"],
                "object_id": nodes[edge["target"]],
                "condition": edge.get("condition"),
                "temporal_kind": "UNKNOWN",
                "verified": True,
                "evidence": [
                    {
                        "knowledge_id": str(knowledge_id),
                        "revision_id": str(revision_id),
                        "quote": edge["evidence"],
                    }
                ],
            },
        )
    result = await api.request(
        "POST", "/api/v1/graph/search", json={"knowledge_id": str(knowledge_id), "max_edges": 100, "depth": 0}
    )
    print(f"Shared graph READY: {len(result['nodes'])} nodes, {len(result['edges'])} edges. Legacy retained.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("knowledge_id", type=UUID)
    parser.add_argument("revision_id", type=UUID)
    args = parser.parse_args()
    asyncio.run(migrate(args.knowledge_id, args.revision_id))


if __name__ == "__main__":
    main()
