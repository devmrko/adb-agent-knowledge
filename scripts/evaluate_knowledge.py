"""Read-only, revision-aware search evaluation. Run with python -m scripts.evaluate_knowledge."""

import argparse
import asyncio
import hashlib
import json
import math
import statistics
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from knowledge_app.contracts import Search
from knowledge_app.mcp_server import KnowledgeAPI, configured_api


class Reference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    knowledge_id: UUID
    revision_id: UUID

    def key(self) -> tuple[str, str]:
        return str(self.knowledge_id), str(self.revision_id)


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    search: Search
    expected: list[Reference]
    forbidden: list[Reference] = Field(default_factory=list)
    split: Literal["dev", "test"]
    origin: str = Field(min_length=1)

    @model_validator(mode="after")
    def consistent(self) -> "Case":
        gold = [r.key() for r in self.expected]
        if len(gold) != len(set(gold)) or set(gold) & {r.key() for r in self.forbidden}:
            raise ValueError("Duplicate or conflicting labels")
        if self.search.include_retired:
            raise ValueError("Evaluation requires default active-only retrieval")
        return self


def load_cases(path: Path) -> list[Case]:
    cases = [Case.model_validate_json(line) for line in path.read_text().splitlines() if line.strip()]
    if not cases or len({c.id for c in cases}) != len(cases):
        raise ValueError("Dataset must be nonempty with unique case IDs")
    groups: dict[str, str] = {}
    for case in cases:
        for ref in case.expected:
            key = str(ref.knowledge_id)
            if key in groups and groups[key] != case.split:
                raise ValueError("Same gold document appears in dev and test")
            groups[key] = case.split
    return cases


def metrics(case: Case, ranked: list[tuple[str, str]]) -> dict[str, float]:
    ranked = list(dict.fromkeys(ranked))
    gold = {r.key() for r in case.expected}
    out = (
        {"forbidden_hit": float(bool(set(ranked) & {r.key() for r in case.forbidden}))}
        if case.forbidden
        else {}
    )
    if not gold:
        return {**out, "no_answer_accuracy": float(not ranked), "false_positive_rate": float(bool(ranked))}
    relevant = [int(ref in gold) for ref in ranked[:5]]
    dcg = sum(rel / math.log2(i + 2) for i, rel in enumerate(relevant))
    ideal = sum(1 / math.log2(i + 2) for i in range(min(5, len(gold))))
    return {
        **out,
        "recall_at_5": len(set(ranked[:5]) & gold) / len(gold),
        "recall_at_20": len(set(ranked[:20]) & gold) / len(gold),
        "hit_at_5": float(any(relevant)),
        "mrr_at_5": next((1 / (i + 1) for i, rel in enumerate(relevant) if rel), 0.0),
        "ndcg_at_5": dcg / ideal,
    }


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    names = sorted({key for row in rows for key in row["metrics"]})
    return {
        "cases": len(rows),
        "metrics": {
            name: statistics.mean(r["metrics"][name] for r in rows if name in r["metrics"]) for name in names
        },
        "denominators": {name: sum(name in r["metrics"] for r in rows) for name in names},
    }


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


async def validate_gold(api: KnowledgeAPI, cases: list[Case]) -> None:
    refs = {r.key() for case in cases for r in case.expected}
    for item_id, revision_id in refs:
        item = await api.request("GET", f"/api/v1/knowledge/{item_id}")
        if (
            item.get("revision_id") != revision_id
            or item.get("status") != "READY"
            or item.get("lifecycle_status") != "ACTIVE"
        ):
            raise ValueError("Gold label is stale, inactive or not ready; review dataset")


async def evaluate(api: KnowledgeAPI, cases: list[Case], repeats: int, warmup: int) -> dict[str, Any]:
    await validate_gold(api, cases)
    rows: list[dict[str, Any]] = []
    latencies: list[float] = []
    profiles: set[str] = set()
    thresholds: set[float | None] = set()
    ranking_configs: set[str] = set()
    first_ms = None
    for case in cases:
        payload = case.search.model_dump(mode="json") | {"top_k": 20}
        if case is cases[0]:
            for _ in range(warmup):
                start = perf_counter()
                await api.request("POST", "/api/v1/knowledge/search", json=payload)
                if first_ms is None:
                    first_ms = (perf_counter() - start) * 1000
        samples = []
        for _ in range(repeats):
            start = perf_counter()
            result = await api.request("POST", "/api/v1/knowledge/search", json=payload)
            elapsed = (perf_counter() - start) * 1000
            latencies.append(elapsed)
            profiles.add(result["profile_id"])
            thresholds.add(result["min_similarity"])
            ranking_configs.add(
                json.dumps(
                    {
                        "score_type": result.get("score_type", "rrf"),
                        "reranker": {
                            k: v
                            for k, v in result.get("reranker", {}).items()
                            if k not in {"candidate_count", "pair_count"}
                        },
                    },
                    sort_keys=True,
                )
            )
            ranked = [(i["knowledge_id"], i["revision_id"]) for i in result["items"]]
            samples.append(
                {
                    "latency_ms": elapsed,
                    "ranked": ranked,
                    "scores": [i.get("rerank_score", i.get("score")) for i in result["items"]],
                    "metrics": metrics(case, ranked),
                }
            )
        names = samples[0]["metrics"]
        rows.append(
            {
                "id": case.id,
                "split": case.split,
                "metrics": {n: statistics.mean(s["metrics"][n] for s in samples) for n in names},
                "samples": samples,
            }
        )
    await validate_gold(api, cases)
    if len(profiles) != 1 or len(ranking_configs) != 1:
        raise ValueError("Embedding profile changed during evaluation")
    return {
        "created_at": datetime.now(UTC).isoformat(),
        "profile_id": next(iter(profiles)),
        "thresholds": sorted(thresholds, key=lambda x: -1 if x is None else x),
        "ranking_config": json.loads(next(iter(ranking_configs))),
        "repeats": repeats,
        "warmup_requests": warmup,
        "first_warmup_ms": first_ms,
        "latency_boundary": "HTTP API round trip including embedding and DB, excluding MCP/Kev",
        "latency_ms": {"p50": percentile(latencies, 0.5), "p95": percentile(latencies, 0.95)},
        "overall": aggregate(rows),
        "splits": {split: aggregate([r for r in rows if r["split"] == split]) for split in ("dev", "test")},
        "cases": rows,
    }


async def run(args: argparse.Namespace) -> None:
    path = Path(args.dataset)
    cases = load_cases(path)
    if args.split != "all":
        cases = [case for case in cases if case.split == args.split]
    if not cases:
        raise ValueError("No cases for requested split")
    report = await evaluate(configured_api(), cases, args.repeats, args.warmup)
    report["dataset_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    output.chmod(0o600)
    print(json.dumps({k: v for k, v in report.items() if k != "cases"}, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset")
    parser.add_argument("--output", default=".run/search-eval/report.json")
    parser.add_argument("--split", choices=["all", "dev", "test"], default="all")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--warmup", type=int, default=1)
    args = parser.parse_args()
    if args.repeats < 1 or args.warmup < 0:
        parser.error("repeats >= 1 and warmup >= 0 required")
    try:
        asyncio.run(run(args))
    except Exception as error:
        parser.exit(
            1,
            f"Evaluation failed ({type(error).__name__}); no successful report written. Check API availability and labels.\n",
        )


if __name__ == "__main__":
    main()
