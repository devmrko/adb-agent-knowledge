# 관계·경로·근거를 함께 검색

기존 공통 RDF/Property Graph 데이터를 재사용한다. DB 변경이나 전체 재추출은 필요 없다.
새 코드는 API와 MCP 모두 업데이트해야 한다. 운영 서버 배포 전 별도 검증이 필요하다.

## 웹

일반 검색 후 목록 위의 **검색 관계 N개 · 근거 보기**를 누른다. 문서 검색 결과와 개체명/별칭
검색 결과의 관계를 함께 표시한다. 문서가 없어도 개체에 연결된 관계는 나올 수 있다.
관계를 누르면 정확한 근거 원문 버전과 인용문을 확인할 수 있다.
카테고리/지식 종류는 직접 문서 검색에 적용된다. 그래프는 사용자와 프로젝트 범위로 제한한다.

## API / MCP

POST /api/v1/knowledge/search 에 include_graph=true를 주면 기존 items에 graph가 추가된다.
MCP knowledge_search는 graph_mode=always로 강제 조회할 수 있다. knowledge_recall도
request.graph_mode=auto/always/never를 지원한다. 민감정보 제한은 always보다 우선한다.

POST /api/v1/graph/search 예시:

```json
{
  "query": "Example App",
  "scopes": ["project:example-app", "project:example-foundation"],
  "direction": "outgoing",
  "predicates": ["uses", "depends_on", "part_of"],
  "depth": 1,
  "max_edges": 20
}
```

- direction: both / outgoing / incoming. 관계 화살표 기준이며 업무상의 상류/하류는 술어 의미에 따라 해석한다.
- depth: 기존 계약 유지. 0은 시작점의 직접 관계, 1은 추가 한 단계(최대 2개 edge 경로).
- include_entity_matches=true이면 query/entity_ids와 seed_revisions를 결합할 수 있다.
  문서와 개체 검색을 각각 수행하고 교대로 합쳐 max_edges에 맞춘다. 의미 점수 기반 리랭킹은 아니다.
- nodes/edges: 관계와 정확한 evidence(지식 ID, 버전, 제목, 인용, 원문 URI).
- paths: entity_ids 및 version_ids 순서. 각 version_id는 edges에 연결되며 최대 100경로이다.
- related_knowledge: 관계에서 발견한 원문 버전 참조. 직접 문서 top-k와 별개이다.
- truncated/paths_truncated: 결과가 제한됐음을 표시한다. 빈 결과나 일부 경로가 전체 부재의 증거는 아니다.
- evidence_state: current_revision_only 또는 historical. 경로는 연결 설명이며 인과/장애 영향의 증명이 아니다.

## 저장·수정·보관 종료

기존 추출 워커와 출처 버전 검사를 유지한다. 현재 검색에서는 활성 원문의 현재 버전 근거만
사용한다. 새 원문이 활성화되면 이전 버전만 뒷받침하던 관계는 현재 검색에서 빠진다.
다른 현재 근거가 있으면 관계는 유지된다. 재추출/검토가 끝나기 전의 누락은 거짓 판정이 아니다.
known_at으로 과거 기록을 조회할 수 있으며 과거 근거를 임의로 최신 버전으로 바꾸지 않는다.
이 기능은 읽기 전용이며 관계를 만들거나 LLM으로 날짜를 추정하지 않는다.

## 검증과 남은 범위

204개 테스트, ruff/mypy 및 JS 문법 검사를 통과했다. 방향/술어/여러 단계 경로,
문서+개체 검색 통합, 사용자 격리, 수정 및 보관 종료의 근거 제외를 검증했다.
브라우저 mock 검증에서 문서 결과가 없는 관계 검색, SVG 렌더링, 원문 근거와 빈 상태를 확인했다.
Oracle 운영 배포 검증과 개체 의미 임베딩, 관계 의미 리랭킹, 자동 전체 인덱스, 근거의 자동
새 버전 이관, 완전 삭제 정책은 이번 변경에 포함하지 않는다. 개체 탐색은 현재 이름·별칭 기반이다.

## 2026-10-29 운영 배포 검증

A10 앱 배포와 API/worker/graph-worker 재시작 완료. 의존성·DB 스키마·자격증명은 변경하지 않았다.
실제 기존 관계에서 문서 3개, 관계 2개, 경로 4개, 근거 원문 2개 반환을 확인했다.
candidate_backend=oracle_property_graph, storage=oracle_rdf 및 source/entity 결합 경로를 확인했다.
강제 recall, 방향/술어 필터, 새 MCP 검색과 HTTPS 웹/JS 배포도 검증했다.
기존 장기 실행 MCP 연결은 재연결해야 새 코드와 계약을 사용한다.
백업: 서버 .run/deploy-related-20261029/before.tar. 실패 시 세 서비스를 중지하고 백업 코드를
복원한 뒤 재시작한다. 백업은 코드이며 DB 복원 파일이 아니다.
