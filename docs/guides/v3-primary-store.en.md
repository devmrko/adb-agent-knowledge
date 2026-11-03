# v3: Primary knowledge content and retrieval in Oracle Agent Memory

[한국어](v3-primary-store.md)

v3 preview 0.3.0 uses a separate Oracle Agent Memory store for business-source JSON and retrieval vectors.
Existing MCP/API behavior and domain history are preserved. This does not remove the application tables.

| Responsibility | v3 storage/behavior |
|---|---|
| Summary, detailed source, provenance JSON | `<store>_MEMORY.CONTENT` |
| Retrieval text and vectors | `<store>_RECORD_CHUNKS` |
| Search | SQL over SDK chunks with existing owner/current/scope/lifecycle filters before ranking; vector + substring keyword RRF, optional reranker |
| Knowledge IDs, current revisions, categories, authorization | Existing vk_item/vk_revision |
| Revision history, audit, retirement/restoration, concurrency | Existing revisions/events/triggers/jobs |
| Original attachments and extraction metadata | Existing revision BLOB and fields |
| Indexes, locations, machine provenance | Existing IDs and source fields |
| Business RDF/Property Graph/evidence/time | Existing vk_g_* and native RDF/Property Graph |
| Agent experiences and memory links | Existing separate AGENT_MEMORY_STORE_ID, normally AKMEMORY |
| Kev, principles and hooks | Unchanged |

Retain vk_revision content and vk_chunk as rollback/compatibility copies. Some evidence-review and audit
operations use these matching copies. Do not delete them. Direct SQL edits do not update all SDK indices
and application history; use supported MCP/API writes. SDK memory relations and business graph relations
are not interchangeable.

## Stable identity

Existing knowledge_id, revision_id, owner_id and graph IDs remain unchanged. A revision gets an immutable
SDK record ID: SHA-256 of the JSON array `[owner, knowledge_id, revision_id]`. The manifest stores this as
sdk_record_id. SDK USER_ID is the authenticated application's owner. Changing K1/R1 creates K1/R2 and a
new SDK record; R1 and its evidence remain available. Names are display values, not keys. Missing agent_id
and thread_id provenance is not invented. The web's source details and selected-item SQL expose the mapping.

## Writes and reads

The existing worker extracts content and stages SDK JSON/chunks/vectors before publication. After verification,
the ACTIVE manifest, current revision, READY status and events commit together in the application transaction.
SDK failure leaves the job FAILED and the previous current version usable. An uncertain SDK write can be retried
using its stable ID. SDK and relational writes are not a distributed transaction: an unpublished SDK orphan may
exist, but it is not searchable without the committed manifest/current pointer. Existing recovery is still needed
for ingestion jobs killed while RUNNING.

Main retrieval joins SDK chunk text/vectors to canonical source IDs and locators. Filters apply before top-k.
This is application SQL over SDK-managed data, not the SDK HYBRID strategy. LIKE is not Oracle Text/BM25.
SDK 26.8 FLOAT64 vectors are normalized to FLOAT32 during exact distance calculation. This is not an ANN
performance claim. Missing current SDK chunks/manifests cause V3_SEARCH_INCOMPLETE rather than partial results.

## Setup, switch and rollback

```sh
./scripts/setup.sh --with-agent-memory
./.venv/bin/alembic upgrade head
./.venv/bin/python -m scripts.source_transfer init
```

The schema head is vk0016. KNOWLEDGE_V3_STORE_ID defaults to AKKNOWLEDGEV3 and must differ from the agent
experience store. Existing installations remain legacy until explicitly switched. For existing data, use the
[transfer CLI](v3-source-transfer.md#english-summary) to enqueue, process, verify and activate required versions.
Then set KNOWLEDGE_SOURCE_BACKEND=v3 and restart **both API and ingestion worker**. For an empty installation,
initialize the store and enable v3 directly. Subsequent new/revised sources are transferred automatically before
READY; no per-revision operator invocation is needed. RDF/Property Graph initialization remains separate.

setup.sh preserves SDK installation when v3 or Agent Memory is enabled in .env/environment. Manual uv sync
needs all required extras: `--extra knowledge --extra mcp --extra agent-memory`.

To roll back the service, stop API/worker, set the backend to legacy and restart both. Keep migrations and SDK
records intact. The retained vectors/content support the legacy path. Per-revision rollback keeps events but may
cause incomplete-search errors in v3; use the global backend setting for a full service rollback. No silent fallback
hides SDK read failures. No source deletion or cleanup is part of this switch.

Existing behavior contracts are rerun against v3. An isolated Oracle test covers real Korean embeddings, new
writes, vector/keyword queries, failed revision publication, retry, historical sources and graphs, retirement,
restoration and original bytes. [Oracle results](../reference/v3-primary-validation.json). These are functional
checks, not large-scale quality, latency or multiprocess crash guarantees.
