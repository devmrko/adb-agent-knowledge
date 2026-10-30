# 업무 흐름 RDF (이전 revision별 형식)

새 관계는 [공통 RDF와 시점별 조회](shared-graph.md)를 사용한다. 아래 API는 기존 원문별 그래프 보존/호환용이다.

Oracle 네이티브 RDF에 업무 관계를 저장한다. DB Companion의 저장/조회 패턴을 참고하며 전용 VK_FLOW_RDF / VK_FLOW를 사용한다. 기존 DBC_* 영역은 공유하거나 수정하지 않는다.

## 설치

API/worker 쓰기를 중지하고 `./uvw run --no-sync alembic upgrade head` →
`./uvw run --no-sync python -m scripts.prepare_knowledge_rdf` 순서로 준비한다.
성공 후 .env의 WORKFLOW_RDF_ENABLED=true를 설정하고 재시작한다.
DDL은 자동 커밋이며 일부만 초기화된 namespace는 확인이 필요하다.
저수준 setup_workflow_rdf는 기존 namespace에 반복 실행하지 않는다.

SQLite는 manifest 기반 테스트 대체만 제공한다. 네이티브 RDF 및 성능 검증은 Oracle에서 수행해야 한다.

## 저장과 조회

1. knowledge_save / knowledge_revise로 원문을 저장한다. workflow_decision에 Kev graph_extract 결과가 붙는다.
2. READY 확인 후 정확한 원문을 읽는다. graph_extract 또는 작업 맥락상 필요한 agent_review이면 에이전트가 근거 있는 관계를 작성한다. Kev는 관계를 생성하지 않는다. 긴 원문은 자동 절단하지 않고 agent_review로 돌린다. URL/파일은 추출 후 별도 판단한다.
3. knowledge_set_workflow에 knowledge_id, revision_id, workflow를 보낸다. 노드 label과 간선 evidence가 원문에 있어야 한다. 조건은 evidence 안에 있어야 한다. verified=true는 관계의 의미까지 추출자가 확인했다는 선언이며 모델 확률을 의미하지 않는다.
4. knowledge_get_workflow로 확인한다. READY일 때 관계 사용 가능하다. 저장은 동기식이며 RDF와 manifest는 같은 트랜잭션에 묶인다.

```json
{"verified":true,"nodes":[{"id":"receive","label":"접수"},{"id":"review","label":"검토"}],"edges":[{"source":"receive","target":"review","relation":"next","evidence":"접수 후 검토"}]}
```

원문은 실제로 “접수 후 검토”를 포함해야 한다. 관계 종류는 next, depends_on, assigned_to, requires, produces. 조건부 전이는 간선 condition 필드로 기록한다. 노드/간선 각각 최대100개, 노드 ID는 영문자로 시작하는 영숫자/밑줄/하이픈 40자 이하다.

동일 revision의 관계는 불변이다. 같은 내용 재요청은 멱등이며, 정정은 새 원문 revision 후 새 관계를 저장한다. 원문 새 버전이 READY가 되면 예전 관계는 기본 조회에서 제외된다. 새 관계가 없으면 ABSENT. 폐기된 지식은 INACTIVE. 서버는 인증 소유자와 활성 버전을 다시 확인한다.

현재 knowledge_search/recall의 관계 확장은 [공통 관계 검색](related-retrieval.md)을 따른다.
HTTP search도 include_graph=true를 지원한다. 이전 revision별 그래프 전체는
knowledge_get_workflow 또는 해당 workflow GET API로 명시적으로 조회한다.
이전 형식에는 업무/기록 시점 계약이 없으므로 공유 그래프의 시점 검색과 혼동하지 않는다.

조회는 RDF accessor SQL로 지정 named graph만 읽어 구조화된 관계를 돌려준다. 임의 SPARQL, 업무 실행, 무제한 경로 추론은 제공하지 않는다. SEM_MATCH/JVM이 필요 없다. 관계 탐색의 답변은 에이전트가 원문 근거와 함께 구성한다.

## Kev 설정과 한계

KEV_GRAPH_LOOKUP_THRESHOLD=0.4, KEV_GRAPH_EXTRACT_THRESHOLD=0.6, KEV_GRAPH_REVIEW_THRESHOLD=0.2는 별도 잠정값이다. 실제 한국어 평가 세트로 정확도를 검증한 값이 아니다. 명시적 graph_mode=always와 직접 workflow 도구는 점수에 막히지 않는다. API 저장은 관계를 자동 추출하지 않으며 MCP/에이전트가 위 순서를 완수해야 한다. 기존 지식의 일괄 관계 추출은 수행하지 않는다.
