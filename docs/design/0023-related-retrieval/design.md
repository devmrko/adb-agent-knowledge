# Evidence-bearing graph retrieval

> 설계 당시의 결정·계획을 보존한 기록입니다. 현재 기본값·설치·지원 범위는 [현재 매뉴얼](../../README.md)을 기준으로 확인하세요. 이 문서의 계획이나 과거 검증은 현재 구현·배포 보장이 아닙니다.

2026-10-29. Approved: return related knowledge, bounded relationship paths and exact evidence
with retrieval; preserve source lifecycle and history. Reuse existing graph, not a second store.

## Contract

GraphSearch adds direction (both/outgoing/incoming), predicate allowlist and opt-in
include_entity_matches. The latter permits query + revision seeds and performs two independent
bounded searches, then merges by assertion version with a single edge budget. Existing source-only
semantics remain unchanged by default. Return seed IDs, paths with version IDs, related source
references, evidence state, and truncation. Paths describe connectivity, not causality.

Recall accepts graph_mode auto/always/never. Always overrides Kev skip; privacy still wins.
REST Search supports include_graph (default false), returning the same evidence graph.
MCP/recall pass the query even when direct source hits exist using the explicit combined mode.
Entity resolution initially uses existing name/alias lookup; semantic entity embeddings are deferred.

## Lifecycle

Current graph evidence must reference an active source's current revision. Edits immediately exclude
old-only evidence from current retrieval; other current supporting sources keep the edge visible.
Retirement excludes that source. known_at retains historical behavior. No read operation publishes
new claims, changes valid dates, merges identities or calls extraction LLMs. Existing asynchronous
extraction handles new active revisions and stale publication checks; this change does not claim
new automatic evidence transfer or hard-delete support. Existing data is queryable without backfill.

## Validation

Direction/predicate filters, bounded multi-hop paths, query+source union, explicit recall override,
owner/scope isolation and edited/retired supporting evidence. Full repo checks. Oracle-specific live
verification remains separate; relational tests do not certify live GRAPH_TABLE execution.
