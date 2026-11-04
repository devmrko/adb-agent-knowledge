"""Read-only target-document evaluation using identical queries for legacy/v3 retrieval."""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from sqlalchemy import func, select

from knowledge_app.database import database
from knowledge_app.embedding import create_embedder
from knowledge_app.models import Item
from knowledge_app.service import KnowledgeService, owner_id
from knowledge_app.settings import Settings
from python_foundation.database import sessions
from python_foundation.security import Actor
from scripts.evaluate_knowledge import aggregate, load_cases, metrics, percentile


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("dataset", type=Path)
    p.add_argument("--issuer", required=True)
    p.add_argument("--subject", required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    cases = load_cases(args.dataset)
    settings = Settings()
    engine = database(settings)
    embedder = create_embedder(settings)
    actor = Actor(args.issuer, args.subject, frozenset())
    services = {
        backend: KnowledgeService(
            sessions(engine), embedder, settings.model_copy(update={"knowledge_source_backend": backend})
        )
        for backend in ["legacy", "v3"]
    }
    rows = {backend: [] for backend in services}
    times = {backend: [] for backend in services}
    report = {
        "date": datetime.now(UTC).isoformat(),
        "dataset_sha256": hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
        "latency_boundary": "warm sequential in-process service, embedding + Oracle; excludes HTTP, MCP, Kev; one sample/query/backend",
        "label_limits": "Conversation-derived normalized questions; exact target documents read; not blind or exhaustive relevance labels. Historical documents count as target retrieval, not current truth.",
    }
    try:
        for case in cases:
            for ref in case.expected:
                item = services["legacy"].get(actor, str(ref.knowledge_id))
                if item["revision_id"] != str(ref.revision_id) or item["status"] != "READY":
                    raise ValueError("Stale gold revision")
        with sessions(engine)() as db:
            report["owner_active_items"] = db.scalar(
                select(func.count())
                .select_from(Item)
                .where(Item.owner_id == owner_id(actor), Item.lifecycle_status == "ACTIVE")
            )
        for service in services.values():
            service.search(actor, cases[0].search.model_copy(update={"top_k": 20}))
        for i, case in enumerate(cases):
            order = ["legacy", "v3"] if i % 2 == 0 else ["v3", "legacy"]
            for backend in order:
                start = perf_counter()
                result = services[backend].search(actor, case.search.model_copy(update={"top_k": 20}))
                elapsed = (perf_counter() - start) * 1000
                ranked = [(r["knowledge_id"], r["revision_id"]) for r in result["items"]]
                rows[backend].append(
                    {"id": case.id, "metrics": metrics(case, ranked), "ranked": ranked, "latency_ms": elapsed}
                )
                times[backend].append(elapsed)
            print(f"Case {i + 1}/{len(cases)}", flush=True)
        report["results"] = {
            b: {
                "quality": aggregate(rows[b]),
                "latency_ms": {"p50": percentile(times[b], 0.5), "p95": percentile(times[b], 0.95)},
                "cases": rows[b],
            }
            for b in services
        }
        report["rankings_equal"] = all(
            a["ranked"] == b["ranked"] for a, b in zip(rows["legacy"], rows["v3"], strict=True)
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        args.output.chmod(0o600)
        print(
            json.dumps(
                {b: {k: v for k, v in report["results"][b].items() if k != "cases"} for b in services},
                ensure_ascii=False,
            )
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
