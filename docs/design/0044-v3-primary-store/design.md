# v3 primary source and search storage

The user requires functional parity, not read-only migration. Preserve public knowledge_id/revision_id,
owner identities, graph IDs, revision/events/audit, retirement/restoration, indexes, summaries,
provenance, attachments, legacy workflow, current/historical evidence, pagination, reranking and filters.
SDK record_id is SHA256 of the existing owner/knowledge/revision tuple, never a new public knowledge ID.
Add sdk_record_id to the manifest and backfill stable IDs in vk0016. Existing source copies remain for
rollback and relational compatibility; this is not deletion or total replacement of domain tables.

In v3 ingestion, stage immutable SDK JSON and vectors before the final relational publication.
Validate SDK exact chunks/vector shape. In the same final UOW as SOURCE_ACTIVATED/READY, publish ACTIVE
manifest and the current source version. SDK failure leaves the job FAILED and the prior active version
searchable. Stable SDK IDs make retry after an uncertain write safe. Existing job recovery remains required
for a killed RUNNING worker. Do not mark READY before SDK validation. Both API and worker use this setup.

Main search uses SDK RECORD_CHUNKS vector and chunk_text columns joined through the manifest to the
canonical item/revision and retained chunk locator IDs. Apply owner/current/lifecycle/scope/category/type/
relation filters BEFORE top-k. Preserve independent substring keyword candidates and RRF/reranking.
This is an application SQL search over SDK-managed vectors, not SDK HYBRID (which requires DB embedder).
Reject missing ACTIVE manifests/chunks in the selected current corpus rather than silently omit sources.
Retain old vectors for rollback only. A changed embedding profile remains an explicit conflict.

RDB remains authoritative for history, identity, lifecycle, audit, attachment bytes and graph/index metadata.
No application generation LLM is added; Kev and agent extraction stay as before. SDK agent_id/thread_id
are optional provenance, not business-document ownership. Existing business records without those values
stay unknown. SQL help must distinguish primary SDK content/vectors and retained compatibility copies.

Validate new ingestion/revision/failure retry, old current retention, SDK candidate source and filters,
keyword exact literals, retired inclusion/restore, exact old version/history/audit/attachment/provenance,
RDF/Property Graph links and MCP/web. Run existing suite + isolated Oracle lifecycle test before deployment.
Do not flip the production read setting until parity tests pass. Initial production copy may proceed.

Oracle validation found SDK FLOAT64 versus app FLOAT32 vector formats. Normalize with
TO_VECTOR(sdk_embedding, 1024, FLOAT32), using a literal dimension (Oracle rejects bound dimensions).
Isolated lifecycle integration passed after this correction. Existing behavior contracts are rerun on v3.
