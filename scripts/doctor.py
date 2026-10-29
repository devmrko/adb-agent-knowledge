"""Read-only installation diagnostics; never display settings or provider exceptions."""

import argparse
import sys
from pathlib import Path

from sqlalchemy import select, text

from knowledge_app.database import database
from knowledge_app.embedding import create_embedder
from knowledge_app.graph_auto_contracts import AutoGraphSettings
from knowledge_app.models import Chunk, Item
from knowledge_app.routing import RoutingSettings
from knowledge_app.settings import Settings


def check(*, db: bool = False) -> int:
    try:
        settings = Settings()
        RoutingSettings()
        graph = AutoGraphSettings()
        embedder = create_embedder(settings)
    except Exception:
        print("FAIL configuration: check provider URL, pinned revision, dimensions and chunk settings")
        return 1
    print(f"OK providers: Kev; embedding={settings.embedding_provider}; dimensions={embedder.dimensions}")
    print(f"OK graph extraction configuration: {graph.mode} (live inference not checked)")
    if settings.database_url.startswith("oracle"):
        wallet = Path(settings.wallet_dir)
        if not all((settings.user_name, settings.user_password.get_secret_value(), settings.oracle_dsn)):
            print("FAIL Oracle: fill USER_NAME, USER_PASSWORD and ORACLE_DSN")
            return 1
        if not all((wallet / name).is_file() for name in ("tnsnames.ora", "ewallet.pem")):
            print("FAIL Wallet: WALLET_DIR must contain tnsnames.ora and ewallet.pem")
            return 1
    if not db:
        print(
            "NOT CHECKED: DB, RDF privileges, live Kev, embedding and extraction. Use --db after migrations."
        )
        return 0
    engine = None
    try:
        engine = database(settings)
        with engine.connect() as connection:
            if engine.dialect.name == "oracle":
                connection.scalar(
                    text("SELECT VECTOR_DISTANCE(TO_VECTOR('[1,0]'), TO_VECTOR('[1,0]'), COSINE) FROM dual")
                )
            profiles = set(
                connection.scalars(
                    select(Chunk.profile_id)
                    .join(
                        Item,
                        (Item.active_revision_id == Chunk.revision_id) & (Item.owner_id == Chunk.owner_id),
                    )
                    .where(Item.lifecycle_status == "ACTIVE")
                    .distinct()
                )
            )
            if profiles - {embedder.profile_id}:
                print(
                    "FAIL embedding profile differs from active stored vectors. Restore original configuration or use a fresh schema."
                )
                return 1
        print("OK DB, schema and active embedding profile compatibility")
        print(
            "NOT CHECKED: live Kev/model inference and RDF/Property Graph initialization; follow onboarding guide"
        )
        return 0
    except Exception:
        print("FAIL DB/schema: check Wallet, credentials, reachability and migrations; details omitted")
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", action="store_true", help="Connect to DB read-only after migrations")
    args = parser.parse_args()
    sys.exit(check(db=args.db))
