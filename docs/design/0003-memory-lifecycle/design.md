# 기억 종류·적용 범위·수정/폐기 이력·관련성 필터

상태: 구현 기준, 2026-10-15. 0001 지식 API와 0002 MCP 위에 기억 관리 기능을 추가한다.

## 목적
문서 검색만으로는 "사용자가 무엇을 결정했고, 무엇을 선호하며, 그것이 언제 바뀌었는가"를 다룰 수 없다.
에이전트가 매 요청마다 과거 지식을 참고할 수 있으려면 (1) 기억의 성격과 적용 범위로 후보를 좁히고,
(2) 바뀐 결정이 옛 내용으로 답변되지 않으며, (3) 관련 없는 결과가 섞이지 않아야 한다.

## 기억 종류 (memory_kind)
DOCUMENT(기본, 참고 문서), DECISION(결정과 근거), PREFERENCE(사용자 선호/관례),
FACT(환경·사실), PROCEDURE(절차/해결 방법), EPISODE(경험). 기존 knowledge_type(NOTE/FAQ/…)은 문서 형식으로 유지한다.
기존 데이터는 DOCUMENT로 이전된다.

## 적용 범위 (scope)
`global`, `project:<key>`, `thread:<key>`, `agent:<key>`(소문자, `[a-z0-9][a-z0-9._-]{0,99}`). 대소문자는 소문자로 정규화한다.
에이전트는 보통 `scopes=["global", "project:<저장소 디렉터리명>"]`으로 검색한다. 기본값은 범위 제한 없음.
범위 계층/와일드카드는 지원하지 않는다.

## 수정·폐기 이력
- VK_ITEM에 lifecycle_status(ACTIVE|RETIRED), superseded_by_id(같은 소유자 항목, 복합 FK),
  retired_at, updated_at 추가.
- VK_REVISION에 revision_no(항목 내 순번, (item_id, revision_no) UNIQUE)와 change_note 추가.
- VK_EVENT(id, owner_id, item_id, event_type CREATED|REVISED|RETIRED|RESTORED, revision_id,
  related_item_id, reason, created_at) 추가. 이벤트는 추가만 하며 수정하지 않는다.
- 수정: `POST /api/v1/knowledge/{id}/revisions` {text, expected_revision_id, change_note} → 새 revision + QUEUED job.
  새 revision이 READY가 되기 전까지 기존 active revision이 계속 검색된다.
  worker는 현재 active보다 revision_no가 큰 경우에만 active를 바꾼다(늦게 끝난 옛 작업이 덮어쓰지 않음).
  동시 수정으로 revision_no가 충돌하면 409 REVISION_CONFLICT.
  RETIRED 항목은 수정할 수 없다(409 KNOWLEDGE_RETIRED); 먼저 복원한다.
- 폐기: `POST /api/v1/knowledge/{id}/retire` {reason, superseded_by?}. ACTIVE→RETIRED 조건부 UPDATE.
  superseded_by는 같은 소유자의 다른 항목이어야 한다. 데이터는 삭제하지 않는다.
- 복원: `POST /api/v1/knowledge/{id}/restore` {reason?}. RETIRED→ACTIVE, 대체 관계 해제.
- 이력: `GET /api/v1/knowledge/{id}/history` → 항목, revision 목록(번호/작성시각/변경 메모/작업 상태/active),
  이벤트 목록. 과거 revision 원문은 기존 content API로 조회한다.
- 물리 삭제 API는 여전히 범위 밖이다.

## 관련성 필터
- 검색 기본값은 ACTIVE 항목만(include_retired=false).
- 필터: memory_kinds, scopes, category, knowledge_type. 모두 후보 검색 SQL에 적용한다.
- 각 청크의 코사인 유사도(Oracle은 1 - VECTOR_DISTANCE COSINE)와 질의어 일치 비율을 계산한다.
  청크별로 유사도 ≥ min_similarity 이거나 질의어(최대 8개)를 모두 포함하는 경우만 통과시키며, 통과한 청크만 항목별로 묶는다.
  후자는 오류 코드처럼 의미 임베딩이 약한 정확 일치를 살리기 위한 것이다.
- 기준값은 SEARCH_MIN_SIMILARITY(기본 0.28), 요청별 min_similarity로 덮어쓸 수 있다(0~1).
  이전 작업자가 소규모 측정을 수행했다고 보고했으나 원본 평가 데이터/결과는 저장소에 없다.
  0.28은 잠정 휴리스틱이며 검증된 정확도 기준으로 주장하지 않는다.
  표본이 작으므로 실제 데이터로 재보정이 필요하며, 긴 청크는 유사도가 낮아질 수 있다.
- 응답에 항목별 similarity, keyword_coverage와 전체 excluded_count, min_similarity를 포함한다.
  순위는 기존 RRF이며 점수는 확률이 아니다.

## MCP
knowledge_save에 memory_kind/scope, knowledge_search에 memory_kinds/scopes/include_retired/min_similarity,
knowledge_list에 필터 추가. 신규 도구 knowledge_revise, knowledge_retire, knowledge_restore, knowledge_history, knowledge_context.
변경 도구는 사용자가 요청했을 때만 호출하도록 설명에 명시한다.

## 에이전트 공통 지침
AGENTS.md "Personal knowledge retrieval on each request"에 요청별 조회 판단 규칙을 둔다(Codex와 Claude Code가 공유).
과거 결정·선호·이전 해결 이력이 답을 바꿀 수 있을 때만 검색하고, 관련 결과가 없으면 언급하지 않으며,
현재 사용자 지시가 저장된 기억보다 우선한다.

## 마이그레이션
vk0002: 열 추가(NOT NULL은 server_default 포함), vk_event 생성, 기존 revision_no=1.
추가형 변경이다. 이력 삭제를 피하기 위해 자동 downgrade는 거부하며 백업/복구 계획을 별도로 검토한다.

## 검증
SQLite: 종류/범위 필터, 폐기 제외/포함, 대체 관계 소유자 검증, 수정 후 READY 전 기존 내용 유지,
옛 작업의 늦은 완료가 active를 되돌리지 않음, 무관 결과 제외와 정확 키워드 예외, 이력/이벤트,
사용자 간 격리(수정/폐기/이력 404). Oracle DDL 컴파일 검사. MCP 도구 계약/요청 경로 검사.

## 구현 보강
- Oracle에서 항목 행 잠금으로 수정/폐기/복원/worker의 active 전환을 직렬화한다.
  수정 요청은 expected_revision_id(가장 최근 revision)를 필수로 보내 오래된 수정 요청을 거부한다.
- create의 idempotency_key는 owner 안에서 유일하다. 동일 입력 재요청은 기존 ID/상태를 반환하고
  다른 입력은 409를 반환한다. 원문을 포함한 요청 해시는 외부에 노출하지 않는다.
- EPISODE 종류 및 thread:<key>/agent:<key> 범위도 허용한다.
- context API/MCP는 검색된 출처의 발췌를 글자 예산 안에 담는다. 생성 요약/영구 스냅샷은 아니다.
- PPTX ZIP/XML에서 실제 presentation 순서와 노트 관계를 따라 텍스트를 추출한다.
  ZIP 압축 해제 크기/항목 수/슬라이드 수를 제한하고 외부 관계는 읽지 않는다.
  청크에 슬라이드 번호(page)와 body/notes를 유지한다. 이미지 OCR은 별도 후속 기능이다.
- 범위 미지정 조회는 호환성을 위해 사용자 전체 범위다. MCP 지침은 현재 프로젝트와 global을
  명시하도록 한다. scope는 사용자 권한과 독립적인 검색 범위이며 인증을 대체하지 않는다.
- 자동 대화 저장, LLM 기억 추출/병합, Graph, DB 고급 보안 기능은 이번 변경 범위 밖이다.
