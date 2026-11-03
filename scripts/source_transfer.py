"""Trusted database-operator CLI for opt-in v3 source transfer (no public endpoint)."""

import argparse
import json
from uuid import UUID

from knowledge_app.agent_memory_repository import SDKRepository
from knowledge_app.database import database
from knowledge_app.embedding import create_embedder
from knowledge_app.graph_service import GraphService
from knowledge_app.service import KnowledgeService
from knowledge_app.settings import Settings
from knowledge_app.source_transfer import SourceTransferService
from knowledge_app.v3_pilot import VersionedMemoryPilot
from python_foundation.database import sessions
from python_foundation.errors import BusinessError
from python_foundation.security import Actor


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=["init", "enqueue", "process", "status", "activate", "rollback", "retry"]
    )
    parser.add_argument("--issuer")
    parser.add_argument("--subject")
    parser.add_argument("--knowledge-id", type=UUID)
    parser.add_argument("--revision-id", type=UUID)
    parser.add_argument("--generation", type=int)
    parser.add_argument("--max-jobs", type=int, default=1)
    args = parser.parse_args()
    if args.action not in {"init", "process"} and not (args.issuer and args.subject and args.revision_id):
        parser.error("This action requires the exact authenticated issuer, subject and revision ID")
    if args.action == "enqueue" and args.knowledge_id is None:
        parser.error("enqueue requires --knowledge-id")
    if args.action in {"activate", "rollback", "retry"} and args.generation is None:
        parser.error("Use status first, then pass --generation")
    if not 1 <= args.max_jobs <= 1000:
        parser.error("--max-jobs must be between 1 and 1000")
    settings = Settings()
    if settings.knowledge_v3_store_id == settings.agent_memory_store_id:
        parser.error("v3 sources require a separate SDK store")
    engine = database(settings)
    embedder = create_embedder(settings)
    sdk = SDKRepository(
        settings.model_copy(update={"agent_memory_store_id": settings.knowledge_v3_store_id}), embedder
    )
    source = KnowledgeService(sessions(engine), embedder, settings)
    transfer = SourceTransferService(
        VersionedMemoryPilot(source, sdk, GraphService(sessions(engine), settings))
    )
    try:
        if args.action == "init":
            sdk.connect(initialize=True)
            result = {"status": "INITIALIZED", "store_id": settings.knowledge_v3_store_id}
        elif args.action == "process":
            processed = 0
            while processed < args.max_jobs and transfer.process_one():
                processed += 1
            result = {
                "processed": processed,
                "note": "Inspect each revision status; processed is not activated",
            }
        else:
            actor = Actor(args.issuer, args.subject, frozenset())
            rid = str(args.revision_id)
            if args.action == "enqueue":
                result = transfer.enqueue(actor, str(args.knowledge_id), rid)
            elif args.action == "status":
                result = transfer.status(actor, rid)
            else:
                result = transfer.change(actor, rid, args.generation, args.action)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except BusinessError:
        raise SystemExit(
            "Source transfer failed. Inspect revision status and configuration; no automatic activation."
        ) from None
    except Exception:
        raise SystemExit(
            "Source transfer unavailable. Check migration, SDK store and provider configuration."
        ) from None
    finally:
        sdk.close()
        engine.dispose()


if __name__ == "__main__":
    main()
