# Agent Memory 연결과 웹 조회

2026-11-02 구현 범위: 선택적 Oracle AI Agent Memory SDK 26.8.0 어댑터,
MCP 저장·검색·프로필 이름 변경, 웹의 전체/에이전트 메모리/업무 지식/관계 그래프 구분.
기존 지식은 자동 이전되지 않으며 memory_kind 분류만으로 SDK 기억으로 간주하지 않는다.


## Oracle SDK와 임베딩 구현의 역할

**Oracle Agent Memory SDK가 이 한국어 임베딩 모델을 기본 제공하는 것은 아니다.**
이 프로젝트가 SDK의 `IEmbedder` 인터페이스를 구현한 `Bridge`를 주입한다.
`OracleDBMemoryStore(embedder=Bridge(), ...)`를 생성하고 그 저장소를
`OracleAgentMemory(store=store, ...)`에 전달한다.

| 구성 요소 | 담당 |
|---|---|
| MCP·Knowledge API | 인증·소유권, 도구 요청, 프로필 이름, 근거 참조 등 서비스 정책 |
| Oracle Agent Memory SDK | 기억 저장·검색 호출, SDK 전용 저장 객체 및 기억 관계 처리 |
| 프로젝트의 IEmbedder Bridge | SDK의 문서/질의 임베딩 요청을 기존 앱 Embedder로 전달 |
| 설정된 임베딩 모델/제공자 | 기억 본문과 질의를 벡터로 변환 |
| Oracle DB | SDK 전용 객체에 기억·벡터·관계를 저장하고 벡터 비교 수행 |
| Kev | 조회·저장 필요성과 경로 판단. 임베딩 생성이나 의미적 진실 판정은 하지 않음 |

```text
저장: MCP memory_save → API → SDK add_memory
      → IEmbedder Bridge → 앱 임베딩 제공자 → 벡터 → Oracle SDK 저장소

검색: MCP memory_search(검색어 있음) → API → SDK search
      → IEmbedder Bridge(is_query=True) → 질의 벡터 → Oracle 벡터 검색

목록: memory_search(검색어 없음) → SDK store.list → 최신 기록 목록
관계: memory_graph → SDK 관계 조회 → 서비스의 권한·범위·깊이 제한 탐색
```

문서/질의 구분은 SDK의 `is_query`를 앱 Embedder의 `query` 인자로 전달하여 유지한다.
목록 조회나 명시적 관계 탐색에 검색어 임베딩을 수행하는 것은 아니다.
SDK 자동 생성형 기억 추출은 `extract_memories=False`로 꺼져 있다.
임베딩은 생성형 LLM과 별도 역할이며, 추출을 꺼도 벡터 저장·검색에는 필요하다.

### 현재 운영 설정과 설치 기본값 구분

2026-11-02 A10 운영 코드·비밀값을 제외한 실제 설정을 확인한 결과:

- 제공자: `EMBEDDING_PROVIDER=local`
- 모델: `dragonkue/snowflake-arctic-embed-l-v2.0-ko`
- 차원: 1024
- 실행 위치: A10 서버의 Knowledge API 프로세스, `EMBEDDING_DEVICE=cpu`
- SDK 저장소: `AGENT_MEMORY_STORE_ID=AKMEMORY`

이는 **우리 배포 설정**이며 Oracle SDK의 고정 모델·기본 실행 위치가 아니다.
SDK 기억 임베딩은 현재 API 요청에서 동기 처리된다. 기존 업무 지식의 비동기 임베딩
워커와 구분해야 한다. 두 경로가 모델 설정을 공유해도 본문·벡터 저장소는 별도다.
모델은 Oracle DB 내부나 Codex·Claude 클라이언트에서 자동 실행되지 않는다.

`EMBEDDING_PROVIDER=openai`를 선택하면 기존 앱 어댑터가 원격 호환 embeddings API에
요청하며 SDK Bridge도 그 제공자를 사용한다. 이 서비스의 원격 경로를 설명하는 것으로,
이번 SDK 운영 검증은 local 설정에서 수행했다.
모델·차원·전처리를 바꾸면 기존 SDK 벡터와 호환된다고 가정하면 안 된다.
현재 서비스는 1024차원이며 자동 재임베딩·무중단 모델 전환은 제공하지 않는다.

구현 근거: [SDK 연결부](../../knowledge_app/agent_memory_repository.py),
[임베딩 제공자](../../knowledge_app/embedding.py), [설정](../../knowledge_app/settings.py).

## 설치

```bash
./uvw sync --extra knowledge --extra mcp --extra agent-memory
./uvw run alembic upgrade head
./.venv/bin/python -m scripts.setup_agent_memory
```

기존 .env의 Oracle 계정과 Wallet을 사용한다. SDK 초기화에는 해당 계정의
CREATE TABLE / PROCEDURE / TRIGGER / PROPERTY GRAPH 권한이 필요하다.
AGENT_MEMORY_STORE_ID=AKMEMORY는 기존 지식과 분리된 SDK 객체 접두사다.
초기화는 CREATE_IF_NECESSARY이고 API 실행은 REQUIRE_EXISTING이다.
삭제·재생성 옵션은 제공하지 않는다. 초기화 성공 후 AGENT_MEMORY_ENABLED=true로 설정하고 API를 재시작한다.
추가 생성형 LLM은 사용하지 않는다. 기존 임베딩 제공자를 SDK 어댑터가 공유한다.

## MCP 사용 순서

1. memory_profiles로 내 에이전트와 대화 이름·버전을 확인한다.
2. memory_profile_save(profile={kind:"agent", key:"tasteby-ops", name:"Tasteby 운영 도우미"})
   로 논리적 에이전트를 만든다. 반환된 id를 사용한다.
3. thread 프로필에 안정적인 세션 key와 제목, agent_id를 지정한다.
4. memory_search로 기존 경험을 찾고 knowledge_prepare_save로 업무 지식 중복도 확인한다.
5. memory_save에 title, text, agent_id, origin_thread_id, scope, idempotency_key를 전달한다.
6. 저장 응답 READY와 memory_search로 결과를 확인한다.

user_id는 입력받지 않고 인증 주체로 결정한다. 같은 key로 이름을 바꿀 때에는
expected_version에 조회한 최신 version을 넣는다. 이름 변경은 ID를 바꾸지 않는다.
프로필 metadata는 읽기·병합하며 기존 키를 유지한다.
동일 소유자의 쓰기는 DB 행 잠금으로 직렬화한다. SDK에 직접 우회 쓰기하면 이 보장이 없다.
SDK 쓰기와 잠금 테이블 트랜잭션은 별개이므로 실패 응답 후에는 상태를 조회한다.
기억 저장은 동일 idempotency_key/동일 본문 재시도만 허용한다.

## 웹

/knowledge의 에이전트 메모리 탭에서 에이전트/대화/범위/과거 포함 필터를 사용한다.
전체 탭은 두 저장소를 별도 목록으로 보여주며 점수를 임의로 섞지 않는다.
메모리는 독립적인 10건 페이지이며 검색은 최대 100건, 목록은 최대 1,000건 범위에서 제공한다.
목록 상한에 도달하면 범위를 좁히라는 안내가 나온다. 동시 추가가 있으면 페이지 구성이 달라질 수 있다.
프로필 선택 목록은 종류별 최대 200건이다.
SDK 미설정·장애는 빈 저장소와 구분한다. 웹은 조회용이며 저장/이름 변경은 MCP로 수행한다.
기존 관계 그래프 탭은 업무 관계를 표시한다. 메모리 상세에는 별도의 기억 관계 그림과 방향·이유 목록을 표시한다. 근거 지식 버튼은 정확한 과거 원문 버전을 열며, 노트의 참조 위치에서는 연결된 기억으로 돌아갈 수 있다.

## 이번에 포함하지 않은 것

- 서로 다른 저장소 점수를 합친 통합 순위
- 기억 본문 수정·은퇴·삭제 MCP, 조직 공유 ACL, 외부 세션 자동 매핑
- 이름 변경의 별도 감사 이력 테이블, 자동 제목 생성

장기 기억은 thread_id로 수명을 묶지 않고 origin_thread_id metadata로 출처를 남긴다.
따라서 대화별 조회는 이 출처 필터를 사용한다. 현재 삭제 도구는 제공하지 않는다.
기존 Kev 판단은 유지한다. knowledge_recall은 SDK 활성화 시 별도 agent_memories 결과를 포함하며 graph_mode와 Kev의 그래프 판단에 따라 관계·근거를 함께 조회한다. include_agent_memory=false로 생략할 수 있다. 민감 입력 표시가 있으면 SDK 추가 검색을 생략한다.

## 검증

전체 275 tests, ruff, format, mypy 통과.
별도 Oracle 계정에서 scripts/smoke_agent_memory.py로 실제 MCP→API→SDK
프로필 생성·이름 변경·저장·중복 방지·목록·한국어 벡터 검색을 검증했다.
이는 모든 OS·대규모 성능 또는 조직 다중 사용자 운영 인증을 증명하지 않는다.

## 근거 연결과 재검토

memory_save 응답의 next_step에 따라 memory_prepare_links로 후보를 찾는다.
호출 에이전트가 정확한 원문 버전과 적용 조건을 확인한 뒤 memory_link_knowledge에
memory_id / knowledge_id / revision_id / quote / reason을 보낸다.
서버는 소유권·현재 버전·정확한 인용을 검증하며 의미의 타당성은 에이전트가 검토한다.
Kev나 검색 점수만으로 확정하지 않는다. 불명확하면 사용자에게 질문한다.

memory_references는 기억→지식 또는 지식→기억을 페이지 조회한다.
원문 변경·은퇴는 조회 시 REVIEW_REQUIRED로 즉시 구분되고 기존 outbox가
MEMORY_EVIDENCE 재검토 항목을 생성한다. 예전 연결은 지우지 않는다.
새 원문을 확인해 새 근거 연결을 추가하고 기존 검토 항목을 이유와 함께 해결한다.
이 과정은 SDK 기억의 내용을 자동 수정하거나 상충 주장의 승자를 결정하지 않는다.
재검토 항목 해결만으로 오래된 근거가 CURRENT가 되지 않는다.

memory_link로 두 기억을 supports/contradicts/supersedes/refines/duplicates로 연결한다.
supersedes/refines/duplicates는 대상 기억을 무효화할 수 있으므로 방향과 의미를 먼저 확인한다.
memory_graph는 양방향으로 탐색하되 응답의 source→target 방향을 보존한다.
기본 1단계, 최대 3단계/100관계로 제한하며 범위·소유권을 모든 끝점에 적용한다.
순환은 방문 집합으로 제한하고 과거 기억의 상태를 숨기지 않는다.

memory_search의 include_connections=true는 상위 최대 5개에 근거와 직접 관계를 포함한다.
knowledge_recall도 graph_mode=always 또는 Kev가 그래프를 선택했을 때 이 경로를 쓴다.
부분 실패는 UNAVAILABLE로 표시하며 업무 지식 결과는 유지한다.
재검토 알림은 기존 knowledge_change_reviews 도구로 조회한다.
이 기능의 자동 연결은 MCP 호출 에이전트가 후보를 검토하고 도구를 실행하는 방식이며,
별도 서비스 LLM이나 무조건적인 유사도 병합을 추가하지 않았다.

추가 마이그레이션: vk0013 (vk_memory_evidence). SDK 기억 본문은 복사하지 않는다.
SDK 스키마의 직접 수정·외부 삭제를 자동 복구하는 기능은 제공하지 않는다.

### SDK 통합 테스트 재현

분리한 테스트 계정(VKV_ 또는 OAM_TEST_ 접두사)만 사용한다. 테스트는 테이블을 준비하고 합성 데이터를 남긴다.

```bash
./.venv/bin/python -m scripts.smoke_agent_memory --env-file /path/to/test.env
# 기존 캐시를 재사용하려면 --hf-home /path/to/huggingface 를 추가
```

특정 개발자 홈 디렉터리에 의존하지 않는다. 캐시를 지정하지 않으면 표준 Hugging Face 환경 설정을 따른다.


## Title correction and readable relationships

memory_rename corrects title metadata only, with memory_id, expected_title, title and reason. It preserves SDK content, embeddings, relationships and validity. Ownership is checked; conflicting titles return a conflict. The last 20 title changes are kept in metadata, not as full content revisions. Same-target retries are idempotent.

The read-only web shows full wrapping titles in relationship cards. Expand the numbered overview for topology and SDK details for raw relation/state values. This does not change Oracle SDK semantics.
