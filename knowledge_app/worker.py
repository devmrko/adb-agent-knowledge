import argparse
import time

from knowledge_app.agent_memory_repository import SDKRepository
from knowledge_app.audit_service import AuditService
from knowledge_app.database import database
from knowledge_app.embedding import create_embedder
from knowledge_app.graph_service import GraphService
from knowledge_app.service import KnowledgeService
from knowledge_app.settings import Settings
from knowledge_app.source_transfer import SourceTransferService
from knowledge_app.v3_pilot import VersionedMemoryPilot
from python_foundation.database import sessions
from python_foundation.web import configure_logging


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    engine = database(settings)
    service = KnowledgeService(sessions(engine), create_embedder(settings), settings)
    sdk = None
    if settings.knowledge_source_backend == "v3":
        if settings.knowledge_v3_store_id == settings.agent_memory_store_id:
            raise ValueError("v3 source store must be separate from agent memories")
        sdk = SDKRepository(
            settings.model_copy(update={"agent_memory_store_id": settings.knowledge_v3_store_id}),
            service.embedder,
        )
        SourceTransferService(
            VersionedMemoryPilot(service, sdk, GraphService(sessions(engine), settings))
        ).attach()
    audit = AuditService(sessions(engine), settings.workflow_rdf_enabled)
    configure_logging()
    try:
        while True:
            processed = service.process_one()
            changed = audit.process_one()
            if args.once:
                break
            if not processed and not changed:
                time.sleep(2)
    finally:
        if sdk is not None:
            sdk.close()
        engine.dispose()


if __name__ == "__main__":
    main()
