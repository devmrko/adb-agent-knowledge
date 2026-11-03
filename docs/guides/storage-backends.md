# 직접 만든 지식 테이블과 Oracle Agent Memory 비교

[English](storage-backends.en.md) · 2026-11-03 · 현재 v2 / v3는 제안 단계

**둘 다 같은 Oracle DB의 테이블에 저장합니다.** Agent Memory는 별도 클라우드 저장소가 아니라,
테이블·청크·검색·기억 관계를 관리하는 Oracle 라이브러리입니다. 차이는 DB 유무가 아니라
**어디까지 우리 코드로 구현하고 어디부터 라이브러리에 맡기느냐**입니다.

## 현재 앱은 어떻게 다른가

| 항목 | 직접 구현한 업무 지식 | 현재 Agent Memory 연결 |
|---|---|---|
| 본문 | vk_revision.content_text (CLOB), summary_text | AKMEMORY_MEMORY.CONTENT (CLOB) |
| 목록·현재 버전 | vk_item, active_revision_id | SDK 레코드/상태. 지식 버전 포인터와 동일하지 않음 |
| JSON 속성 | tags_json/sources_json 등 앱 필드 | AKMEMORY_MEMORY.METADATA (native JSON) |
| 검색 청크·벡터 | vk_chunk.text / embedding (VECTOR) | AKMEMORY_RECORD_CHUNKS.CHUNK_TEXT / EMBEDDING (VECTOR) |
| 현재 검색 방식 | 코사인 벡터 후보 + LIKE 부분문자열 후보, 앱에서 순위 합산 | SDK 벡터 검색. 임의 metadata 필터는 SDK 기능이며 공개 MCP에는 범위/대화 등 일부만 노출 |
| Oracle Text 사용 여부 | 현재 사용 안 함. LIKE는 Oracle Text/BM25가 아님 | 현재 벡터 구성에서 사용 안 함. SDK의 별도 검색 전략은 아래 참조 |
| 임베딩 위치 | 저장은 워커, 질의는 API의 설정된 임베딩 제공자 | API → SDK Bridge → 같은 설정의 임베딩 제공자 |
| 기본 모델 | dragonkue/snowflake-arctic-embed-l-v2.0-ko, 1024차원 | 같은 앱 모델을 주입. Oracle SDK 자체 기본 모델이라는 뜻이 아님 |
| 관계 | vk_g_* 기준 데이터 + native RDF, 선택적 SQL Property Graph | AKMEMORY_MEMORY_LINK의 기억 관계 + SDK 그래프 지원 |
| 근거 | 정확한 지식 ID/원문 버전/인용 | vk_memory_evidence로 업무 지식 원문에 연결 |
| 저장·수정 관리 | 앱의 버전·충돌·멱등성·작업·변경 이력 | SDK 저장 기능 + 앱 소유권·멱등성 보완. 본문 수정/은퇴 MCP는 미제공 |

AKMEMORY는 이 프로젝트의 기본 AGENT_MEMORY_STORE_ID 접두사입니다. 다른 설치는 달라질 수 있습니다.
모델은 EMBEDDING_PROVIDER=local이면 API/worker 머신, 원격이면 설정한 임베딩 서버에서 실행합니다.
현재 기본 구성에서 DB 내부에 이 모델을 설치하는 것이 아닙니다. SQL 벡터 비교는 Oracle에서 수행합니다.

## 어떤 키로 구분하나

| 의미 | 업무 지식 | Agent Memory / 이 앱의 규약 |
|---|---|---|
| 저장소 이름 | 앱 테이블 집합 | memory_store_id: 객체 접두사. 사용자 ID가 아님 |
| 사용자 | owner_id | USER_ID에 앱의 인증 소유자 ID 저장 |
| 항목 ID | vk_item.id → API knowledge_id | RECORD_ID → API memory_id |
| 원문 버전 | vk_revision.id, revision_no | 같은 의미의 자동 원문 버전 키가 현재 연결에 없음 |
| 청크 | vk_chunk.id, revision_id, chunk_no | CHUNK_ID, SOURCE_ID, SOURCE_RECORD_TYPE, CHUNK_SEQ |
| 에이전트 | 필요 시 출처/연결로 관리 | AGENT_ID |
| 대화 | 원본 출처로 관리 | SDK THREAD_ID. 이 앱의 장기 기억은 metadata.origin_thread_id로 출처 기록 |
| 프로젝트 | scope 열: project:example | metadata.scope: project:example (SDK 예약 필드가 아닌 앱 규약) |
| 사람이 보는 제목 | vk_item.title | metadata.title (ID와 별개) |
| 관계 | claim/version/entity ID | RELATION_ID, SOURCE_MEMORY_ID, TARGET_MEMORY_ID, RELATION_TYPE |

owner_id/USER_ID는 API 키나 DB 접속 사용자명이 아닙니다. 앱이 인증 주체에서 계산합니다.
현재 memory_id는 소유자·멱등 키로 계산한 안정적인 ID입니다. 제목이 같아도 같은 기억이라는 뜻은 아닙니다.
THREAD_ID와 origin_thread_id는 같지 않습니다. 현재 앱은 대화 삭제가 장기 기억의 수명을 결정하지 않도록
출처를 metadata로 관리합니다. 프로젝트 범위도 권한 자체가 아니며 소유권 검사가 별도로 필요합니다.

## ‘벡터 / 키워드 / JSON / 그래프 검색’의 차이

| 방식 | 질문 예 | 실제 비교 대상 |
|---|---|---|
| 벡터 | ‘배포가 실패하면 어떻게 복구하지?’ | 임베딩한 질의와 저장 검색 청크의 의미적 거리 |
| LIKE 키워드 | ‘ORA-01017’ 포함 기록 | 문자 포함 여부. 현재 업무 지식의 보조 경로 |
| Oracle Text | 단어 기반 전문 검색 | Text 인덱스와 lexer에 따른 텍스트 검색. 현재 앱에서 미활성 |
| JSON 키 필터 | project=tasteby, review.status=confirmed | 저장한 속성 값. 의미 유사도가 아님 |
| 그래프 | ‘이 프로젝트가 쓰는 서비스는?’ | 등록된 개체·관계와 근거. DB가 문서에서 관계를 자동 추론하지 않음 |

Oracle Agent Memory26.8은 VECTOR / KEYWORD / HYBRID 전략을 제공합니다.
KEYWORD는 DB 텍스트 검색 기반이며 임베딩 제공자 없이 사용할 수 있습니다.
HYBRID는 관리되는 Oracle Hybrid Vector Index를 사용하고 **OracleDBEmbedder를 요구**합니다.
따라서 현재 외부 한국어 모델 구성을 그대로 둔 채 HYBRID만 켤 수 있다고 안내하면 잘못입니다.
우리 앱은 이 전략 선택을 공개 설정으로 구현하지 않았고 한국어 Oracle Text 검색 품질도 검증하지 않았습니다.

SDK가 저장한 content와 의미 검색용 index_texts는 다르게 지정할 수 있습니다.
JSON 본문을 보관하면서 섹션별 자연어를 색인하고, metadata로 프로젝트 조건을 걸 수 있습니다.
metadata 변경만으로 그 값이 자동 벡터화되지 않습니다. 자세한 [JSON 실험 결과](agent-memory-json-evaluation.md)를 참고하세요.

## SDK를 쓰면 무엇을 덜 만들고, 무엇은 남나

SDK에 청크/벡터 저장, 기본 검색, 기억 관계와 상태 관리의 일부를 맡길 수 있습니다.
대신 SDK 버전·스키마·검색 전략의 제약을 따라야 합니다. 직접 테이블을 구성하면 계약을 자유롭게
설계할 수 있지만 색인 갱신·검색·삭제 정합성 등을 우리 코드에서 책임져야 합니다.

어느 쪽이든 인증, 업무별 JSON 검증, 정확한 원문 이력, 멱등성/충돌, 근거 재검토와 조직 권한은
자동 해결되지 않습니다. SDK를 쓰는 것만으로 검색이 더 정확하거나 더 빠르다고 검증한 것은 아닙니다.
기억 사이의 supports/supersedes와 프로젝트의 uses/deployed_on은 의미가 달라 일괄 치환하면 안 됩니다.

## v3 제안: 사용자 창구와 저장 기반 통합

현재 버전은 v2 preview(0.2.0)입니다. **v3는 설계·검증할 다음 버전 이름이며 아직 출시/이관하지 않았습니다.**

제안 목표는 사용자가 기억/업무 지식 저장소를 고르지 않아도 하나의 저장·검색 창구를 쓰고,
Agent Memory를 공통 본문·검색 저장 기반으로 활용하는 것입니다. Kev, 임베딩 제공자 선택,
RDF·Property Graph와 정확한 근거·이력은 유지합니다.

1. JSON 규약: content에 요약·상세·출처, metadata에 필터 키, index_texts에 검색 청크.
2. 버전 계약: 논리 지식 ID와 불변 버전 ID를 유지. 덮어쓰기로 과거 근거를 잃지 않게 설계.
3. 문서3건의 작은 이관 시험: 이전/새 버전, 검색, 정확한 인용, 그래프 현재성, 실패 재시도와 되돌리기 비교.
4. 검색 전략 결정: 외부 한국어 임베딩 유지 시 벡터+별도 키워드 조합 검증. Oracle HYBRID는 별도 후보.
5. 검증 통과 후 이관 도구·호환 API·복구 절차를 갖추고 v3 전환. 기존 v2 운영 경로는 그때까지 유지.

현재 JSON 약4MiB 왕복 시험은 저장 가능성만 확인했습니다. 전체 이관 승인이나 검색 품질 동등성 증명이 아닙니다.
패키지 버전/태그/운영 데이터는 이 문서 추가로 변경하지 않습니다.

## 근거

- 현재 코드: knowledge_app/repository.py, models.py, agent_memory_repository.py, agent_memory_service.py
- [SDK 검색/저장 전략](https://docs.oracle.com/en/database/oracle/agent-memory/26.8/guide/api/agentmemory.html)
- [Store의 본문·검색 텍스트·필터](https://docs.oracle.com/en/database/oracle/agent-memory/26.8/guide/api/stores.html)
- [JSON 검증](agent-memory-json-evaluation.md) / [그래프 역할과 SQL](oracle-graph-examples.md)
