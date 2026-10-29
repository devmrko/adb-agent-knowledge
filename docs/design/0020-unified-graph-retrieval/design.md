# 벡터 → 공통 관계 → 근거 검색

2026-10-19. 사용자가 승인한 Oracle 통합 검색 개선 설계.

## 기준 데이터

vk_g_entity.id를 공통 개체 ID로, vk_g_version과 vk_g_evidence를 관계 및 정확한 원문 버전의 기준으로 유지한다. RDF는 기존 트랜잭션에서 동기화되는 표현이다. SQL Property Graph는 기존 테이블의 조회 View이며 독립적인 쓰기 저장소가 아니다. 관계 추출이나 이름 유사도만으로 개체를 병합하지 않는다.

## 검색 계약

GraphSearch에 최대 10개의 seed_revisions(knowledge_id, revision_id)을 추가한다. 첫 단계는 해당 원문 버전이 근거인 관계로 제한한다. 이후 기존 개체 ID를 따라 확장한다. 각 관계에 retrieval_level을 반환한다. 기존 knowledge_id 단독 조회는 호환 유지. 두 종류의 원문 시작점은 동시 지정 불가.

knowledge_recall도 직접 검색 결과가 있으면 동일한 원문 버전 시작점을 사용한다. 인덱스만 탐색한 경우 순위 없는 목록 전체를 시작점으로 삼지 않고 이름 검색을 유지한다.

MCP knowledge_search는 Kev가 그래프 조회를 선택했을 때 검색 결과 상위 3개의 정확한 버전을 시작점으로 사용한다. 검색 결과가 없으면 기존 이름 검색을 유지한다. 날짜 지정 시 현재 벡터 결과가 역사 검색을 제한하지 않도록 기존 이름 검색을 유지한다. 벡터 점수와 그래프 연결을 같은 점수로 합치지 않는다. 그래프 관계는 영향 확정이 아닌 근거가 있는 연결이다.

## Oracle Property Graph

VK_KG_ENTITIES / VK_KG_RELATIONS View와 VK_KNOWLEDGE_GRAPH를 만든다. 객체 간 관계만 포함하며 literal은 기존 RDB/RDF 경로로 처리한다. 과거 관계 버전도 보존한다. PROPERTY_GRAPH_ENABLED는 기본 false. 활성화 시 개체 frontier의 관계 후보를 GRAPH_TABLE로 찾고, 기존 RDB 조건으로 owner/scope/시간을 제한한 다음 정확한 근거 및 RDF를 검증한다. 오류 시 무제한 검색이나 권한 완화로 fallback하지 않는다.

그래프 및 View는 모든 소유자의 내부 데이터를 포함하므로 API 사용자에게 DB 객체를 직접 공개하지 않는다. 기존 DB 서비스 계정만 사용한다. DDL은 설치 도구에서 명시적으로 실행하며 서비스 시작 중 자동 실행하지 않는다.

## 검증

다른 원문 버전/사용자/범위의 관계 배제, 연결 확장, 회수된 근거, 순환/상한, 기존 시간 검색을 테스트한다. Oracle DDL/GRAPH_TABLE은 실 DB에서 별도 확인한다. SQLite 성공을 Oracle 성공으로 보고하지 않는다.

## 참고 조사와 후속 범위

- Cognee: 자료를 연결된 기억으로 수집하고 검색 경로를 선택. https://github.com/topoteretes/cognee
- Graphiti: 에피소드 근거, 시간별 관계 및 혼합 검색. https://github.com/getzep/graphiti
- Oracle SQL Property Graph: https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/create-property-graph.html

이는 설계 원본 자료이며 개인 기억 DB의 대체 사본이 아니다. 비교 자료는 공식 문서 검토이며 직접 성능 비교는 수행하지 않았다. 동일 개체 자동 판정, 충돌/대체 자동 판단, 세션 기억 정리는 후속 설계 대상으로 남긴다. 이번 단계는 기존 정체성과 근거를 연결하는 검색 및 Property Graph 조회 경로를 구현한다.
