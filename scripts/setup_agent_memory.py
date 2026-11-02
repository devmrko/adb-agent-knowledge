"""Explicit, additive initialization of the optional SDK store; never recreate."""

from knowledge_app.agent_memory_repository import SDKRepository
from knowledge_app.embedding import create_embedder
from knowledge_app.settings import Settings


def main() -> None:
    settings = Settings()
    repository = SDKRepository(settings, create_embedder(settings))
    try:
        repository.connect(initialize=True)
        print("Agent memory SDK schema ready:", settings.agent_memory_store_id)
    except Exception as exc:
        print("Agent memory initialization failed:", type(exc).__name__)
        raise SystemExit(1) from None
    finally:
        repository.close()


if __name__ == "__main__":
    main()
