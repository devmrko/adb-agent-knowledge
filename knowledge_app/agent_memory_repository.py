"""SDK boundary. No provider exceptions or credentials cross this boundary."""

import asyncio
import importlib
import threading
from pathlib import Path
from typing import Any

from knowledge_app.embedding import Embedder
from knowledge_app.settings import ROOT, Settings


class SDKRepository:
    def __init__(self, settings: Settings, embedder: Embedder) -> None:
        self.settings, self.embedder = settings, embedder
        self._lock = threading.Lock()
        self._store: Any = None
        self._client: Any = None
        self._pool: Any = None

    def connect(self, *, initialize: bool = False) -> None:
        with self._lock:
            if self._store is not None:
                return
            core = importlib.import_module("oracleagentmemory.core")
            base = importlib.import_module("oracleagentmemory.apis.embedders").IEmbedder
            np = importlib.import_module("numpy")
            app_embedder = self.embedder

            class Bridge(base):  # type: ignore[misc, valid-type]
                embedding_dimension = app_embedder.dimensions
                max_input_tokens = 8192

                def embed(self, texts: list[str], *, is_query: bool = False) -> Any:
                    return np.asarray(app_embedder.encode(texts, query=is_query), dtype=np.float32)

                async def embed_async(self, texts: list[str], *, is_query: bool = False) -> Any:
                    return await asyncio.to_thread(self.embed, texts, is_query=is_query)

            s = self.settings
            wallet = Path(s.wallet_dir).expanduser()
            if not wallet.is_absolute():
                wallet = ROOT / wallet
            odb = importlib.import_module("oracledb")
            pool = odb.create_pool(
                user=s.user_name,
                password=s.user_password.get_secret_value(),
                dsn=s.oracle_dsn,
                config_dir=str(wallet),
                wallet_location=str(wallet),
                wallet_password=s.wallet_password.get_secret_value() if s.wallet_password else None,
                min=1,
                max=3,
                increment=1,
                tcp_connect_timeout=10,
                retry_count=0,
            )
            try:
                store = core.OracleDBMemoryStore(
                    embedder=Bridge(),
                    pool=pool,
                    memory_store_id=s.agent_memory_store_id,
                    schema_policy=core.SchemaPolicy.CREATE_IF_NECESSARY
                    if initialize
                    else core.SchemaPolicy.REQUIRE_EXISTING,
                    vector_dim=s.embedding_dimensions,
                )
                client = core.OracleAgentMemory(
                    store=store,
                    memory_extraction_config=core.MemoryExtractionConfig(extract_memories=False),
                )
            except Exception:
                pool.close()
                raise
            self._pool, self._store, self._client = pool, store, client

    @property
    def store(self) -> Any:
        self.connect()
        return self._store

    @property
    def client(self) -> Any:
        self.connect()
        return self._client

    def verify_source_index(self, record_id: str, owner: str, chunks: list[str]) -> bool:
        """Read-only exact chunk and vector-shape check for a staged source."""
        import math

        self.connect()
        prefix = self.settings.agent_memory_store_id
        with self._pool.acquire() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT chunk_text, embedding FROM {prefix}_RECORD_CHUNKS WHERE source_id=:id AND user_id=:owner AND source_record_type='memory' ORDER BY chunk_seq",
                    id=record_id,
                    owner=owner,
                )
                rows = cursor.fetchall()
                texts = [v.read() if hasattr(v, "read") else v for v, _ in rows]
                return (
                    texts == chunks
                    and all(
                        vector is not None
                        and len(vector) == self.settings.embedding_dimensions
                        and all(math.isfinite(v) for v in vector)
                        and any(vector)
                        for _, vector in rows
                    )
                    and bool(rows)
                )

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
        if self._pool is not None:
            self._pool.close()
