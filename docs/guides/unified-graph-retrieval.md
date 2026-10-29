# Oracle 통합 그래프 검색

## 기준 데이터와 조회 흐름

노트·벡터 청크의 원문 버전 → vk_g_evidence → vk_g_version → vk_g_entity의 공통 ID를 따라 검색한다. RDF는 기존 관계 의미/근거 표현으로 유지한다. SQL Property Graph는 관계 테이블을 직접 읽는 View이므로 별도 관계 복제나 동기화 작업이 없다.

knowledge_search와 knowledge_recall에서 그래프 조회를 선택하면 직접 검색된 상위 3개 노트의 정확한 버전과 질의의 개체 이름·별칭 검색을 각각 시작점으로 사용한다. 두 결과를 제한된 관계 예산 안에서 합치고 인접 관계를 확장한다. 날짜가 지정된 knowledge_search는 현재 벡터 결과로 역사 검색을 제한하지 않는다.

각 관계의 retrieval_level=0은 시작 원문의 관계, 1 이상은 추가 확장 단계다. evidence에는 정확한 knowledge_id/revision_id/quote/content_uri가 있다. 원문 조회로 확인한 뒤 답변 근거로 사용한다. 그래프 연결을 벡터 점수에 합산하거나 영향의 확정으로 취급하지 않는다. depth는 기존 계약대로 시작 관계를 포함하고 이후 최대 depth번 확장한다. max_edges와 truncated를 확인한다.

## 다른 머신/Oracle에 설치

기존 마이그레이션과 RDF 초기화 후 실행한다.

```sh
./.venv/bin/python -m scripts.setup_property_graph
./.venv/bin/python -m scripts.setup_property_graph --apply
```

첫 명령은 메타데이터/권한 확인만 한다. --apply는 VK_KG_ENTITIES, VK_KG_RELATIONS, VK_KNOWLEDGE_GRAPH를 생성/재정의한다. Oracle DDL은 자동 커밋된다. 관계 데이터는 변경하지 않는다. CREATE PROPERTY GRAPH 및 View 생성 권한이 필요하다. 설치가 완료되면 .env에 PROPERTY_GRAPH_ENABLED=true를 설정하고 서비스를 재시작한다. false는 기존 관계형 탐색을 사용한다.

Property Graph는 개체 간 관계만 다룬다. literal 관계는 기존 RDB/RDF 경로로 유지한다. 기록/업무 시점, scope, 소유자, 활성 근거 검증은 서비스에서 수행한다. View에는 과거 버전도 포함되므로 직접 조회할 때 현재 관계라고 가정하지 않는다. DB 객체를 최종 사용자에게 직접 grant하거나 노출하지 않는다.

## 검증과 제한

2026-10-19 실제 Oracle에서 View/SQL Property Graph 생성, GRAPH_TABLE 실행, 같은 합성 데이터의 RDB/Property Graph 결과 일치, 원문 버전 시작점, 두 관계 확장, 다른 사용자 격리, 관계 회수/이력을 검증했다. 합성 데이터는 외부 트랜잭션에서 롤백했다. 대용량 성능 우위는 측정하지 않았다. Property Graph 활성 상태에서 오류가 나면 기존 권한 필터를 우회하지 않고 조회 실패를 반환한다.

동일 개체 자동 병합, 의미적 모순/대체 자동 판정, 장기 영향 분석은 아직 구현하지 않았다. 현재 공통 ID 및 검증된 관계를 재사용한다. API /api/v1/graph/search는 seed_revisions를 지원한다. 일반 /api/v1/knowledge/search도 include_graph=true로 통합 관계를 요청할 수 있으며 MCP 및 recall 경로에서도 조합한다.

[설계·외부 조사 출처](../design/0020-unified-graph-retrieval/design.md)
