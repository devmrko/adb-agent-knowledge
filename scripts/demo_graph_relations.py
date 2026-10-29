"""Explicitly create a small fictional Cafesto graph through the authenticated API."""

import argparse
import asyncio
import json
from typing import Any

from knowledge_app.mcp_server import KnowledgeAPI, configured_api

SCOPE = "project:graph-demo"
SOURCE = (
    "[설명용 가상 예시] Cafesto UX는 Cafesto의 일부다. "
    "Cafesto는 TypeScript Foundation에서 생성됐다. "
    "Cafesto UX의 별칭은 Cafesto UI다. 실제 프로젝트 구성에 대한 주장이 아니다."
)


async def run(api: KnowledgeAPI) -> dict[str, Any]:
    saved = await api.request(
        "POST",
        "/api/v1/knowledge",
        json={
            "title": "[설명용] Cafesto 그래프 예제",
            "text": SOURCE,
            "scope": SCOPE,
            "idempotency_key": "cafesto-graph-demo-v1",
            "category": "그래프 예제",
        },
    )
    for _ in range(90):
        job = await api.request("GET", f"/api/v1/jobs/{saved['job_id']}")
        if job["status"] == "READY":
            break
        if job["status"] == "FAILED":
            raise RuntimeError("Demo indexing failed; inspect job status")
        await asyncio.sleep(1)
    else:
        raise RuntimeError("Demo indexing pending; inspect job before rerunning")
    kid, rid = saved["knowledge_id"], saved["revision_id"]
    prepared = await api.request(
        "POST", f"/api/v1/graph/extraction/knowledge/{kid}/prepare", json={"expected_revision_id": rid}
    )
    if prepared["text"] != SOURCE:
        raise RuntimeError("Demo source changed; inspect exact content before reuse")
    review = prepared["review"]
    if review["status"] != "COMPLETE":
        review = await api.request(
            "POST",
            f"/api/v1/graph/reviews/{kid}",
            json={
                "revision_id": rid,
                "expected_version": review["version"],
                "status": "REVIEWING",
                "note": "Explicit demonstration: inspecting the complete fictional source",
            },
        )
    ids = {}
    for key, label, kind in [
        ("ux", "Cafesto UX", "project_area"),
        ("app", "Cafesto", "project"),
        ("foundation", "TypeScript Foundation", "template"),
    ]:
        entity = await api.request(
            "POST",
            "/api/v1/graph/entities",
            json={
                "scope": SCOPE,
                "identity_key": "demo:cafesto:" + key,
                "label": label,
                "kind": kind,
            },
        )
        ids[key] = entity["id"]
    evidence = {"knowledge_id": kid, "revision_id": rid, "quote": SOURCE}
    assertions = []
    for subject, predicate, target in [("ux", "part_of", "app"), ("app", "created_from", "foundation")]:
        assertions.append(
            await api.request(
                "POST",
                "/api/v1/graph/assertions",
                json={
                    "scope": SCOPE,
                    "subject_id": ids[subject],
                    "predicate": predicate,
                    "object_id": ids[target],
                    "verified": True,
                    "evidence": [evidence],
                },
            )
        )
    candidates = await api.request(
        "POST",
        "/api/v1/graph/identities/resolve",
        json={
            "query": "Cafesto UI",
            "scopes": [SCOPE],
            "namespace": "display-name",
        },
    )
    if not any(c["exact"] and c["entity"]["id"] == ids["ux"] for c in candidates["items"]):
        await api.request(
            "POST",
            "/api/v1/graph/identities",
            json={
                "entity_id": ids["ux"],
                "kind": "alias",
                "namespace": "display-name",
                "value": "Cafesto UI",
                "expected_version": 0,
                "evidence": evidence,
                "note": "Alias explicitly stated in fictional demo source",
            },
        )
    if review["status"] != "COMPLETE":
        await api.request(
            "POST",
            f"/api/v1/graph/reviews/{kid}",
            json={
                "revision_id": rid,
                "expected_version": review["version"],
                "status": "COMPLETE",
                "outcome": "RELATIONS",
                "note": "Complete fictional source reviewed; two supported relationships registered",
            },
        )
    results = {}
    for intent, seed in [("evidence", "ux"), ("dependencies", "foundation")]:
        results[intent] = await api.request(
            "POST",
            "/api/v1/graph/explore",
            json={
                "intent": intent,
                "search": {"entity_ids": [ids[seed]], "scopes": [SCOPE], "depth": 2},
            },
        )
    return {
        "knowledge_id": kid,
        "revision_id": rid,
        "entities": ids,
        "assertions": assertions,
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Store fictional source, entities and relations")
    args = parser.parse_args()
    if not args.apply:
        print(
            "No writes. --apply creates fictional data in project:graph-demo; API and embedding worker must run."
        )
        return
    try:
        result = asyncio.run(run(configured_api()))
    except Exception:
        raise SystemExit(
            "Demo did not finish. Inspect source/job/review status before retrying; credentials omitted."
        ) from None
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
