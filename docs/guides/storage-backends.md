# 직접 만든 지식 테이블과 Oracle Agent Memory 비교

[English](storage-backends.en.md) · 2026-11-04 · v3 알파 기준 / 아래 legacy 표는 별도 구분

현재 v3 구현: [SDK 원문·검색과 기존 업무 이력을 함께 운영](v3-primary-store.md). 아래 표는 legacy 업무 지식과 에이전트 경험 메모리의 비교입니다.
**둘 다 같은 Oracle DB의 테이블에 저장합니다.** Agent Memory는 별도 클라우드 저장소가 아니라,
테이블·청크·검색·기억 관계를 관리하는 Oracle 라이브러리입니다. 차이는 DB 유무가 아니라
**어디까지 우리 코드로 구현하고 어디부터 라이브러리에 맡기느냐**입니다.

## 장단점과 현재 v3 판단 (2026-11-04)

**Agent Memory의 주된 이점은 공통 기억 기능의 재사용입니다. 검색 속도나 임베딩 제거가 아닙니다.**
현재 v3의 업무 지식 경로와 별도 에이전트 경험 기억 경로를 구분해야 합니다.

| 항목 | 벡터 테이블 + 직접 구현 | Agent Memory 활용 |
|---|---|---|
| 구현 편의 | 원문·청크·벡터·메타데이터·검색 코드를 직접 관리 | 공통 저장 구조·검색·사용자/에이전트/스레드·기억 관계 API 재사용 |
| 임베딩 | 모델과 호출·청크 연결을 직접 구성 | 설정한 임베더 호출 또는 사전 계산 벡터 입력. 모델 연산 자체는 필요 |
| 검색 선택 | SQL·필터·순위·인덱스를 직접 통제 | SDK의 VECTOR/KEYWORD/HYBRID 계약·스키마 제약에 맞춤 |
| 업무 계약 | 원하는 버전·권한·감사를 설계 | 우리의 불변 원문·정확 인용·감사·업무 그래프 계약은 별도 유지 |
| 운영·유지보수 | 직접 관리할 코드가 많지만 동작 통제가 쉬움 | 공통 코드 재사용, 대신 라이브러리 버전·관리 스키마 변경 대응 필요 |
| 현재 v3 부담 | 기존 단일 원문/청크 경로 | SDK 저장소와 호환·복구 사본을 함께 유지해 공간·쓰기 부담 증가 |

### 임베딩을 따로 준비하지 않아도 되나요?

아닙니다. SDK가 임베딩 호출을 맡아줄 수 있지만, 벡터 검색에는 모델 또는 미리 계산한 벡터가 필요합니다.
현재 Bridge는 앱의 같은 한국어 1024차원 임베딩 제공자를 호출합니다. 기본 실행 위치는 API/워커 머신이며
원격 제공자를 선택할 수도 있습니다. Oracle 안에서 이 한국어 모델이 자동으로 실행되는 것은 아닙니다.
KEYWORD 검색은 임베더 없이 가능하지만 의미 기반 벡터 검색과 다릅니다.

### 현재 v3가 SDK 검색을 그대로 사용하나요?

- **업무 지식:** Agent Memory의 원문/청크/벡터를 사용하되 우리 애플리케이션 SQL로 검색합니다. 소유자·현재 버전·범위·수명 필터 후 벡터+LIKE 후보 순위를 결합합니다.
- **에이전트 경험 기억:** SDK 검색 API를 사용하고 별도 기억 관계를 탐색합니다.
- **업무 그래프·이력:** 기존 vk_g_*·RDF·Property Graph·버전·감사·작업 관리가 남습니다.

SDK 자체의 HYBRID는 OracleDBEmbedder를 요구하므로 외부 한국어 임베더에 옵션만 켜서 적용할 수 없습니다.
SDK 기능 전체가 현재 MCP에 노출된 것도 아닙니다. 이 프로젝트의 선택은 [v3 구조](v3-primary-store.md)를 따릅니다.

### 검색 속도·품질 실측

2026-11-03 같은 모델·질의·대상 문서를 사용한 30질의 비교입니다.

| 지표 | 직접 테이블(legacy) | Agent Memory 기반 v3 |
|---|---:|---:|
| 중앙값 | 260.54ms | 283.49ms |
| p95 | 289.52ms | 310.86ms |
| 정답 문서 상위5 포함 | 22/30 | 22/30 |
| 정답 문서 상위20 포함 | 28/30 | 28/30 |
| 반환 순위 | 두 방식 동일 | 두 방식 동일 |

측정 경계는 예열된 단일 프로세스의 임베딩+Oracle 서비스 호출이며 HTTP/MCP/Kev/그래프는 제외했습니다.
질의별·방식별 1회, 순차·교대 실행입니다. 대화 주제를 바탕으로 에이전트가 작성한 질의와 문서별 정답 라벨이며
독립·완전한 관련성 평가가 아닙니다. 당시 소유자 활성 지식은320건이지만 전체가 질의별 범위에 들어간다는 뜻은 아닙니다.
같은 검색 알고리즘과 임베딩을 유지했으므로 SDK 자체의 검색 전략 품질 비교로 해석하면 안 됩니다.
이 표본에서 v3가 약23ms 느렸으나 통계적 유의성·대규모 성능·원인별 기여를 측정하지 않았습니다.
[개인 식별자를 제거한 결과](../reference/storage-backend-comparison.json) · [비교 스크립트](../../scripts/compare_search_backends.py).
재실행에는 실행자의 DB·인증 소유자·허용된 질의/정답 문서 세트가 필요합니다. 원본 개인 자료는 배포하지 않습니다.

### 저장·수정 비용에서 남은 개선

알파 코드 확인 결과, `KnowledgeService.process_one`은 호환 경로의 벡터를 먼저 생성하고 v3 staging을 호출합니다.
`VersionedMemoryPilot.stage_owned`는 새 SDK 레코드에 청크를 전달하지만 계산한 벡터는 전달하지 않아 SDK가
Bridge를 통해 다시 임베딩합니다. 기존 SDK 레코드 재사용은 별도 경로입니다. 따라서 **새 원문 저장에서 중복
임베딩 경로가 존재**합니다. 이는 코드 확인이며 임베딩 호출 횟수 계측이나 저장 지연 벤치마크 결과는 아닙니다.

복구용 원문·벡터 사본과 SDK 원문·벡터를 함께 보관합니다. v3 검색에는 FLOAT64 저장 벡터를 FLOAT32로
맞추는 SQL 변환도 있습니다. 위 검색 시간 차이가 이 변환 때문이라고 원인을 확정하지 않습니다.
SDK는 사전 계산 벡터를 받을 수 있으므로, 다음 개선 후보는 벡터 재사용→저장·수정 시간 측정→복구 사본 정책 검토입니다.
이 문서 변경으로 최적화를 구현하거나 사본을 제거하지 않았습니다.

### 어떤 경우에 선택하나요?

단순 업무 문서 검색과 직접 SQL 최적화가 중심이면 직접 테이블 방식도 적합합니다. 사용자·에이전트·대화·경험 기억을
공통 API로 확장하려면 Agent Memory의 재사용 가치가 커집니다. 우리 프로젝트는 Oracle 에이전트 기억 활용이라는
목적에 맞춰 v3를 선택했지만, 현재 장점은 공통 기반과 확장성이고 속도·운영 단순화 이점은 제한적입니다.

구현 근거: [워커](../../knowledge_app/service.py), [SDK staging](../../knowledge_app/v3_pilot.py),
[임베더 Bridge](../../knowledge_app/agent_memory_repository.py), [검색 SQL](../../knowledge_app/repository.py).
공식 계약: [저장·사전 계산 벡터](https://docs.oracle.com/en/database/oracle/agent-memory/26.8/guide/api/stores.html),
[검색 전략·임베더](https://docs.oracle.com/en/database/oracle/agent-memory/26.8/guide/api/agentmemory.html).

## legacy 업무 지식과 에이전트 경험 기억의 구조 비교

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

## 최초 v3 제안 (과거 설계): 사용자 창구와 저장 기반 통합

당시 버전은 v2 preview(0.2.0)이었고 v3는 제안 단계였습니다. 아래는 최초 계획이며 현재 구현은 위 v3 안내를 참조하세요.

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

### v3 구현 진행

[버전별 JSON 저장·그래프 연결 파일럿](v3-pilot.md)이 추가됐습니다. 초기 시험 기록이며 현재 주 경로 구현은 위 v3 안내를 참조하세요.
