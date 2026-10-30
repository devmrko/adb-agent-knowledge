# Evidence-backed identity and resumable agent review

> 설계 당시의 결정·계획을 보존한 기록입니다. 현재 기본값·설치·지원 범위는 [현재 매뉴얼](../../README.md)을 기준으로 확인하세요. 이 문서의 계획이나 과거 검증은 현재 구현·배포 보장이 아닙니다.

Scope approved 2026-10-30: retain Kev, improve entity identification and useful RDF/Property Graph
retrieval, track review of active source versions. No Kev comparison, Oracle Text, automatic entity
merge, new inference engine, or change to original source identity. Public repo only; deploy after validation.

Add vk0010: graph review rows per source revision, identity bindings, append-only change records.
Review PENDING -> REVIEWING -> COMPLETE/FAILED, with optimistic version checks. COMPLETE distinguishes
RELATIONS vs NONE, requires exact current source, and existing current evidence for RELATIONS; NONE
is rejected if current evidence exists. UNRESOLVED stays FAILED for follow-up. Interrupted REVIEWING
can be reclaimed explicitly using its current version. Every transition records actor and note.
Activation of a source creates PENDING in the ingestion transaction; older active sources without rows
remain discoverable as pending and are materialized on explicit review. Retired/noncurrent sources are
excluded from backlog; their review history remains. No hidden worker or LLM.

Identity bindings: confirmed alias or external identifier plus namespace and exact active source evidence.
External keys are unique per owner/scope/namespace/value. Alias bindings allow multiple entities;
ambiguity returns candidates, never merges. Every write has expected_version (0=create) and a note.
Corrections/retractions preserve immutable snapshots. Source changes invalidate a binding's use as a
confirmed match until evidence is refreshed. Scope is context, ownership is authorization.
Candidate resolution prioritizes exact canonical identity and active proven bindings; fuzzy label/legacy
alias results remain hints. No embedding-based entity resolution claimed in this increment.

Expose bounded HTTP/MCP review backlog, transition, history, identity bind/resolve/history and graph
explore intent. Evidence intent follows documents/part_of/created_from; dependencies follows incoming
uses/depends_on/created_from/deployed_on/part_of. Existing bounded graph search owns visibility,
current/historical evidence and depth. SQL Property Graph remains optional candidate traversal over
canonical relational records; RDF mirrors facts/evidence. These intents do not claim separate SPARQL
inference: source evidence and graph connectivity are not semantic truth or proven impact.

Document supported roles, lifecycle, migration, installation, and runnable RDF/Property Graph setup
and Cafesto example. Tests: auth/isolation, stale evidence, conflicts, alias ambiguity, identity
correction history, revision backlog, no-facts completion, interrupted review, graph intent filters,
SQLite migration plus Oracle DDL compilation. Live Oracle claims require actual separate validation.

## Validation and delivery boundaries

2026-10-30: full suite (249 tests) passed before final bounded-query optimization; final checks repeated
for the changed code. New migration tested from vk0001 with existing source preserved. Oracle table DDL
compiled; live Oracle migration is not claimed. Cafesto demo tested twice against the actual SQLite API
and ingestion service: source idempotency, two-edge traversal, alias binding and review completion.
No deployment or installed-client change in this increment; the public repository skill is updated.
RDF/Property Graph direct SQL examples follow current checked-in setup/query implementation; actual
Oracle privileges and execution remain an environment-specific validation step.
