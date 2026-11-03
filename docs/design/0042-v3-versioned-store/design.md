# v3 versioned Agent Memory pilot

Stage: opt-in, isolated pilot; no production routing change or package release.

Preserve knowledge_id/revision_id as graph/evidence keys. Store a validated JSON source envelope
in a distinct Agent Memory store, with deterministic owner+knowledge+revision IDs, content digest
and embedding profile. Existing IDs continue to resolve through the v2 authority during validation.
Never update an imported revision in place. Exact retries reuse it; conflicting payloads fail.
Read checks owner, key and digest. Search uses SDK vectors, validates records and filters against
current v2 lifecycle/revision after retrieval; report bounded candidate exhaustion rather than
claiming complete recall. Current graph traversal seeds exact source IDs and retains RDF verification
and Property Graph candidate behavior. No memory relation is silently translated into a business edge.

This pilot deliberately keeps v2 source copies for comparison/rollback; it is not the final canonical
storage migration. No automatic dual-write, new public MCP tools, source deletion or live deployment.
Missing/failed staging cannot activate data. Cross-store writes are not one transaction.
Rollback means returning to unchanged v2 routing; never deleting history to simulate rollback.

Verify three synthetic documents, Korean model retrieval, immutable revision staging, exact retry,
wrong-owner read, corrupt digest, old source preservation, current-evidence exclusion after revision,
new evidence graph/RDF, Property Graph vs relational traversal, and v2 fallback. Remaining release gates:
durable staging job and activation transaction, backfill/resume, full extraction/file provenance mapping,
keyword parity, unbounded-history candidate handling, multi-process races, and independent v3 graph source resolver.
