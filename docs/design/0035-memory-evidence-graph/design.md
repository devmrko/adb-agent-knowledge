# 0035 — 기억 근거와 관계 탐색
2026-11-02 구현 전 설계. 0034의 두 번째 단계.

## 계약
- memory_prepare_links: 기존 기억 본문으로 업무 지식 후보 조회. 쓰기 없음. 후보 점수는 근거 확인이 아님.
- memory_link_knowledge: memory_id, knowledge_id, revision_id, quote, reason을 받아 같은 소유자의 현재 원문/정확한 인용 검사 후 연결. 의미 확인은 호출 에이전트 책임.
- memory_references: 기억→지식 / 지식→기억을 페이지 조회. 현재 원문과 비교해 CURRENT / REVIEW_REQUIRED 표시.
- memory_link: 같은 소유자의 두 SDK 기억을 supports/contradicts/supersedes/refines/duplicates로 연결. 명시적 의미 검토와 이유 필요.
- memory_graph: 지정 기억에서 제한된 양방향 BFS. 관계 방향과 과거 상태를 보존.
- knowledge_recall은 기존 결과를 유지하며 선택적 agent_memories 필드로 SDK 결과를 함께 반환. 점수 혼합 없음.

## 저장과 일관성
vk_memory_evidence: immutable evidence tuple (memory, knowledge, revision, quote, reason), deterministic id for retry;
owner-scoped relational foreign keys; SDK memory is checked by service because cross-system FK unavailable.
Old rows are retained. New source revision requires a new evidence row. No automatic semantic approval.
Existing vk_item change outbox creates MEMORY_EVIDENCE review tasks on update/retire/direct changes.
Read-time currentness checks prevent stale evidence being reported current even before outbox runs.
Outbox opens review but does not alter SDK truth/status. No distributed transaction is claimed.
A missing/deleted/retired source remains unavailable or historical; never substitute another user's record.
No body duplication: only quote and exact reference are stored.

SDK links have deterministic IDs and owner metadata. Record existence/ownership is checked before link creation and
for every graph endpoint. Retry returns existing matching relation, conflicting payload is rejected.
SDK operations may partially succeed; inspect relation state on uncertainty.
Historical endpoints remain explicitly invalid. Contradictions do not pick a winner.
Traversal is bounded by depth/edges/nodes and reports truncation. Scope filters apply to every endpoint.

## UI
Memory detail shows source cards (title/revision/currentness/quote) and memory relationship SVG with accessible list.
Selecting evidence opens the exact knowledge revision, not silently latest. Knowledge references show linked memories.
Web remains read-only. Automatic connection means agent-assisted candidate review through MCP, not server LLM guessing.

## Validation
Tests: owner isolation including linked results, exact quote and revision mismatch, retired sources,
stale read before outbox, outbox review idempotency, graph cycles/depth/limit, link retries,
partial memory-store failure in unified recall, browser evidence navigation.
Then isolated Oracle/MCP smoke; deploy additive migration and API/worker; public HTTPS smoke.
