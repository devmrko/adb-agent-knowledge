# Oracle Agent Memory SDK and embedding responsibilities

The Korean embedding model is **not a built-in default supplied by Oracle Agent Memory SDK**.
This project implements the SDK's `IEmbedder` interface as `Bridge`, passes it to
`OracleDBMemoryStore(embedder=Bridge(), ...)`, and supplies that store to `OracleAgentMemory`.

The SDK manages memory persistence, retrieval and memory relations. Our Bridge delegates
embedding to the application's configured provider. Oracle stores the resulting vectors and
performs vector comparisons. MCP/API enforce application authentication and ownership.
Kev decides whether and how to retrieve/store; it does not produce embeddings.

```text
Save:   MCP → API → SDK add_memory → IEmbedder Bridge → application embedder → Oracle
Search: MCP → API → SDK search → Bridge(is_query=True) → query vector → Oracle vector search
Browse: no query → SDK store.list
Graph:  SDK relation lookup → bounded application traversal with ownership/scope checks
```

Verified deployment on 2026-11-02: local provider,
`dragonkue/snowflake-arctic-embed-l-v2.0-ko`, 1024 dimensions, CPU in the Knowledge API
process on A10, SDK store `AKMEMORY`. These are **our deployment settings**, not fixed SDK defaults.
The model does not run inside Oracle or automatically on the Codex/Claude client.
SDK-memory embedding is synchronous in the API; existing business-document ingestion uses its
separate asynchronous worker. Sharing embedding configuration does not merge their storage.

The adapter preserves SDK `is_query` as the application embedder's `query` flag.
`extract_memories=False` disables SDK generative extraction, not vector embedding.
The optional `EMBEDDING_PROVIDER=openai` configuration delegates to the existing remote
OpenAI-compatible embeddings provider; this SDK deployment was verified with the local provider.
Changing models/preprocessing does not make old vectors compatible automatically.
The application currently requires 1024 dimensions and has no automatic re-embedding migration.

Implementation: [SDK adapter](../../knowledge_app/agent_memory_repository.py),
[embedding provider](../../knowledge_app/embedding.py), [settings](../../knowledge_app/settings.py).
For setup, tools and limits, see [the detailed guide](agent-memory.md).
