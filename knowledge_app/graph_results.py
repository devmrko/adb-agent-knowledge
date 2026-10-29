"""Bounded, deterministic graph result formatting; never infer facts from a path."""

from typing import Any


def enrich_graph(result: dict[str, Any], direction: str, depth: int) -> dict[str, Any]:
    edges = result["edges"]
    adjacency: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for edge in edges:
        if direction != "incoming":
            adjacency.setdefault(edge["source"], []).append((edge["target"], edge))
        if direction != "outgoing":
            adjacency.setdefault(edge["target"], []).append((edge["source"], edge))
    paths: list[dict[str, Any]] = []
    queue: list[tuple[list[str], list[str]]] = [
        ([seed], []) for seed in sorted(result.get("seed_entity_ids", []))
    ]
    cursor = 0
    while cursor < len(queue) and len(paths) < 100:
        nodes, versions = queue[cursor]
        cursor += 1
        if len(versions) >= depth + 1:
            continue
        for target, edge in adjacency.get(nodes[-1], []):
            if target in nodes:
                continue
            new_nodes, new_versions = nodes + [target], versions + [edge["version_id"]]
            paths.append({"entity_ids": new_nodes, "version_ids": new_versions, "hops": len(new_versions)})
            queue.append((new_nodes, new_versions))
            if len(paths) >= 100:
                break
    references: dict[tuple[str, str], dict[str, Any]] = {}
    for edge in edges:
        for evidence in edge["evidence"]:
            key = (evidence["knowledge_id"], evidence["revision_id"])
            ref = references.setdefault(key, {k: v for k, v in evidence.items() if k != "quote"})
            ref.setdefault("assertion_ids", [])
            if edge["assertion_id"] not in ref["assertion_ids"]:
                ref["assertion_ids"].append(edge["assertion_id"])
    result.update(
        paths=paths,
        paths_truncated=len(paths) >= 100,
        related_knowledge=list(references.values()),
        direction=direction,
        path_semantics="connectivity_only_not_causal_proof",
    )
    return result
