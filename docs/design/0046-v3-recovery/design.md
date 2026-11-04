# v3 recovery validation

Use an explicitly named isolated VKV_/OAM_TEST_ schema with no queued/running jobs.
No production worker or database connection is interrupted. Parent creates synthetic sources; a
child runs the existing ingestion code. Parent SIGKILLs only that child (1) after SDK staging and
(2) after the final relational transaction is flushed but before commit. For connection-loss testing,
close the child's real Oracle driver connection inside the final transaction, then force an SQL
operation. This tests a lost connection, not a firewall outage or prolonged database unavailability.

Require: previous source/search remains current, history retained, unpublished SDK source invisible,
shipped recover_knowledge_jobs requeues RUNNING only after child exit, normal worker --once publishes
exactly once with stable SDK record ID, repeated processing adds no events. FAILED connection-loss
jobs use the supported retry path. No automatic recovery is claimed: RUNNING crash recovery remains
an explicit operator procedure with all workers stopped. Capture sanitized pass labels and timing.

Also assess search with a frozen, synthetic 30-query corpus (label as synthetic, not real-user ground
truth), real embedding/Oracle latency and legacy/v3 comparison. Validate Claude with real CLI prompts
and document client authentication blockers. Prepare a clearly scoped preview release after checks.

Live Claude follow-up exposed a 35s hook timeout: recall took ~26s while direct source search took
~0.28s. Provider failure opened the first two catalog indexes without relevance evidence. Remove
that arbitrary browsing fallback: keep direct retrieval and return the catalog for agent selection.
Successful Kev index selection and explicit index IDs remain unchanged. Add a no-browse-on-failure
regression test; do not increase the hook timeout to hide the cause.

After API restart restored Kev navigation, automatic graph expansion cost 32.86s versus 1.08s
for knowledge plus memories without expansion. Mandatory prompt preflight defaults graph_mode=never;
return an explicit deferred-graph marker so the agent expands relations on demand through MCP. This
retains index routing and both memory stores. Operators may opt into auto/always via hook config.
No claims that graph latency is solved; it is deferred to intentional graph work.


## Restore the verified native RDF graph filter

The public checkout and current deployment still compare GET_MODEL() per row.
Restore the previously verified shared_rdf G_ID query from the original checkout.
Resolve the bound owner/version graph URI through RDF_VALUE$, select the whole named
graph by stored G_ID, and only then decode triples. Preserve the 301-row overflow
guard, exact set comparison, ownership/version URI, and unexpected-triple detection.
No schema or public contract changes. Compare identical graph-enabled API requests
and returned graph/evidence before and after deployment. Do not attribute all recall
latency to this query without measurement. Workflow and navigation RDF are separate
paths and remain outside this restoration.


### Native RDF restoration result

Same production direct recall with graph_mode=always and both memory stores: before
19.888s; after restart first call 12.809s, subsequent calls 1.376s and 1.387s.
All six edges, nodes, evidence, paths and agent memories matched exactly. Only
automatically generated valid_at/known_at query timestamps differed. Small sample,
not an SQL-only benchmark or a cold-start latency guarantee. No data/DDL changes.
The temporary hook graph_mode=never default is superseded: default is auto again,
with optional configuration. Kev still chooses whether relations are useful.
Ruff, formatting, mypy and all 345 tests passed before this default restoration.
