import argparse
import time

from knowledge_app.audit_service import AuditService
from knowledge_app.database import database
from knowledge_app.embedding import create_embedder
from knowledge_app.service import KnowledgeService
from knowledge_app.settings import Settings
from python_foundation.database import sessions
from python_foundation.web import configure_logging


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    engine = database(settings)
    service = KnowledgeService(sessions(engine), create_embedder(settings), settings)
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
        engine.dispose()


if __name__ == "__main__":
    main()
