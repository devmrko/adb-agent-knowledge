# Application-owned tables versus Oracle Agent Memory

[한국어](storage-backends.md) · 2026-11-03 · Current v2; proposed v3

**Both store data in Oracle tables.** Agent Memory is a library managing schema, retrieval rows,
search and memory relationships—not a separate cloud database. The distinction is who implements the behavior.

| Area | Current business knowledge implementation | Current Agent Memory integration |
|---|---|---|
| Content | vk_revision.content_text / summary_text (CLOB) | AKMEMORY_MEMORY.CONTENT (CLOB) |
| Metadata | Application fields such as tags_json/sources_json | AKMEMORY_MEMORY.METADATA (native JSON) |
| Chunks/vectors | vk_chunk.text / embedding | AKMEMORY_RECORD_CHUNKS.CHUNK_TEXT / EMBEDDING |
| Search today | Cosine vector candidates + LIKE substring candidates, application rank fusion | SDK vector search; scoped metadata filters |
| Oracle Text today | Not enabled; LIKE is not Oracle Text/BM25 | Not enabled in this vector configuration |
| Embedding | Worker for ingestion, API for queries | API → SDK IEmbedder Bridge → configured application embedder |
| Default model | dragonkue/snowflake-arctic-embed-l-v2.0-ko,1024 dimensions | Same injected application model; not an SDK built-in default |
| Relationships | vk_g_* + native RDF + optional SQL Property Graph | AKMEMORY_MEMORY_LINK + SDK graph support |
| Evidence | Exact source revision and quotation | vk_memory_evidence references business knowledge revisions |
| Lifecycle | Application revisions, concurrency, jobs and history | SDK records/status plus app ownership/idempotency; no public body revise/retire MCP yet |

AKMEMORY is the default AGENT_MEMORY_STORE_ID prefix, not universal. Local embedding runs on the
API/worker host; remote embedding runs at the configured provider. Oracle performs vector comparison.

## Identifiers and keys

| Meaning | Business knowledge | Agent Memory / application convention |
|---|---|---|
| Store | Application table set | memory_store_id: DB object prefix |
| Owner | owner_id | USER_ID: authenticated application owner |
| Record | vk_item.id / knowledge_id | RECORD_ID / memory_id |
| Source revision | vk_revision.id, revision_no | No equivalent immutable source revision contract in this integration |
| Chunk | id, revision_id, chunk_no | CHUNK_ID, SOURCE_ID, SOURCE_RECORD_TYPE, CHUNK_SEQ |
| Agent | Source/reference context | AGENT_ID |
| Conversation | Source metadata | SDK THREAD_ID; this app uses metadata.origin_thread_id for durable-memory provenance |
| Project | scope column | metadata.scope (app convention) |
| Display title | title column | metadata.title (app convention) |
| Relationship | claim/version/entity IDs | RELATION_ID, SOURCE_MEMORY_ID, TARGET_MEMORY_ID, RELATION_TYPE |

USER_ID is not an API key or database login. The app derives it from the authenticated actor.
Current memory IDs are stable IDs derived from owner and idempotency keys. Titles are not identifiers.
Project scope is not authorization. origin_thread_id is not the SDK THREAD_ID lifecycle binding.

## Search modes are different

- **Vector:** semantic similarity between a query embedding and retrieval chunks.
- **LIKE:** substring matching, used as the current business-knowledge keyword branch.
- **Oracle Text:** indexed full-text retrieval with lexer behavior; not currently enabled here.
- **JSON filter:** matching metadata keys/values, not semantic similarity.
- **Graph:** following stored relationships/evidence, not automatic document understanding.

SDK 26.8 offers VECTOR, KEYWORD and HYBRID strategies. KEYWORD uses DB text retrieval without requiring
an embedder. HYBRID uses the managed Oracle hybrid vector index and requires OracleDBEmbedder.
It cannot simply be enabled with the current external Korean embedder. This application does not expose
SDK strategy selection as a public setting; Korean Oracle Text quality has not been validated.

Stored content and retrieval text can differ: keep JSON content, index natural-language sections,
and constrain results with metadata. Metadata changes do not automatically embed those values.
See the [JSON experiment](agent-memory-json-evaluation.md).

The SDK can reduce custom chunk/vector/search plumbing, but brings version/schema/strategy constraints.
Neither approach removes application authorization, domain validation, immutable evidence/history,
concurrency control or review workflows. No speed or accuracy superiority has been established.
Memory supports/supersedes relationships are not interchangeable with business uses/deployed_on edges.

## Proposed v3

Current release remains v2 preview(0.2.0). **v3 is a design/validation proposal, not a released migration.**
Unify the user-facing save/search entry point and evaluate Agent Memory as the common content/retrieval
backend. Retain Kev, embedding-provider choice, RDF/Property Graph and exact evidence/history.

1. Define JSON content, filter metadata and retrieval chunk contracts.
2. Preserve logical knowledge IDs and immutable revision IDs; do not overwrite historical evidence.
3. Pilot three documents with old/new revisions, retrieval, quotations, graph validity, retries and rollback.
4. Validate external Korean vector + keyword options separately from an Oracle HYBRID alternative.
5. Only after validation, provide migration tooling, compatible APIs and recovery before v3 cutover.

The 4MiB JSON round-trip experiment proves storage feasibility only. No package version, release tag or
production data is changed by this proposal.

Sources: current models/repository/agent_memory_repository/agent_memory_service code;
[SDK API](https://docs.oracle.com/en/database/oracle/agent-memory/26.8/guide/api/agentmemory.html),
[Store semantics](https://docs.oracle.com/en/database/oracle/agent-memory/26.8/guide/api/stores.html).
