"""Separate consumer so LLM latency never blocks source embedding or outbox work."""

import argparse
import time

from knowledge_app.database import database
from knowledge_app.graph_auto_service import AutoGraphService
from knowledge_app.settings import Settings
from python_foundation.database import sessions


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    engine = database(settings)
    service = AutoGraphService(sessions(engine), settings)
    try:
        while True:
            processed = service.process_one()
            if args.once:
                break
            if not processed:
                time.sleep(3)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
