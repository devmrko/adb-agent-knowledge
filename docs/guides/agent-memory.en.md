# Agent memory (Oracle AI Agent Memory)

[Application-owned tables vs Agent Memory: storage, keys, search and proposed v3](storage-backends.en.md)


The user-facing feature is **agent memory**: experiences, preferences and previous work memories. SDK refers to the development library used to connect it, not the name of a memory category.

## What does Agent Memory search?

Stored content, semantic retrieval text and metadata filters have different jobs.
For a deployment procedure, the SDK can keep structured content while indexing readable sections.
These are SDK capabilities; the current MCP does not expose all of these inputs.

| Field | Example | Purpose |
|---|---|---|
| content | JSON string containing summary, sections and sources | Original content returned to the reader |
| index_texts | Deployment checks and recovery steps as separate text chunks | Text embedded for semantic retrieval |
| metadata | project=tasteby, review.status=confirmed, tags=[deployment] | Exact structured conditions that constrain results |

A project filter selects matching values; a question such as “How do I recover a failed deployment?”
compares meaning through embeddings. Adding a metadata key does not automatically embed its value.
When retrieval text is overridden, it determines what can be found semantically. Indexing only the summary
can miss details; include relevant sections as chunks. Search can return the original logical record,
so the application must bound or paginate large returned content.

The current integration calls add_memory(text, ...) and uses the application's configured embedder.
An empty query lists records. Ownership and optional project/agent/thread filters constrain retrieval;
relationships use separate bounded traversal. Memory scores are not merged with business knowledge scores.

### Current app, SDK capabilities and measured limits

- **Current MCP:** text is limited to 12,000 characters and title to 120. Arbitrary metadata JSON and
  index_texts inputs are not exposed.
- **SDK 26.8:** nested metadata and array filters, separate retrieval text and caller-owned chunks are
  supported. Serialize a memory body as a JSON string; a direct Python dict was rejected in this experiment.
- **Measured storage:** Korean/emoji JSON content and metadata each round-tripped at about 4MiB.
  This is a tested size, not the maximum or a recommended production size. Synthetic vectors were used;
  semantic quality and real-model long-input behavior were not measured.
- **Database capacity:** native JSON has a 32MB limit; CLOB has a separate limit. Model token limits,
  HTTP limits and SDK behavior are separate constraints.
- **Updates:** metadata replaces the entire object; it is not a deep merge and does not automatically
  re-embed values. Content plus index_text updates replaced persisted chunks/vectors in the test.
  This is not immutable application revision history.
- **Hybrid retrieval:** SDK HYBRID requires OracleDBEmbedder. It cannot simply be enabled with the
  current external Korean embedder, and differs from the business knowledge vector+LIKE implementation.

Business knowledge can be represented here, but exact source versions, quotations and RDF relationships
still require application contracts. Production data has not been migrated.
See the [JSON feasibility report (Korean)](agent-memory-json-evaluation.md) and
[machine-readable experiment results](../reference/agent-memory-json-probe.json).
Official references: [store semantics](https://docs.oracle.com/en/database/oracle/agent-memory/26.8/guide/api/stores.html),
[search configuration](https://docs.oracle.com/en/database/oracle/agent-memory/26.8/guide/api/agentmemory.html),
[Oracle datatype limits](https://docs.oracle.com/en/database/oracle/oracle-database/26/refrn/datatype-limits.html).


## SDK integration and embedding responsibilities

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
Agent-memory embedding is synchronous in the API; existing business-document ingestion uses its
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


## Title correction and readable relationships

memory_rename corrects title metadata only, with memory_id, expected_title, title and reason. It preserves SDK content, embeddings, relationships and validity. Ownership is checked; conflicting titles return a conflict. The last 20 title changes are kept in metadata, not as full content revisions. Same-target retries are idempotent.

The read-only web shows full wrapping titles in relationship cards. Expand the numbered overview for topology and memory record details for raw relation/state values. This does not change Oracle SDK semantics.
