# 공통 RDF와 시점별 조회

노트는 관계의 근거다. 개체와 관계는 노트 밖에서 재사용하며 여러 원문이 같은 관계를 보완할 수 있다. 기존 코드 원문/편집 화면은 유지한다.

## 설치와 업그레이드

Oracle 사용자는 기존 .env 접속 설정을 사용한다. API·워커의 쓰기를 중지하고
`./uvw run --no-sync alembic upgrade head` 후
`./uvw run --no-sync python -m scripts.prepare_knowledge_rdf`를 실행한다.
이 진입점은 VK_FLOW_RDF와 VK_FLOW/VK_SHARED/VK_NAV를 준비하며 정상적인 기존 객체는 유지한다.
일부만 초기화된 namespace는 자동 교체하지 않고 중단한다. WORKFLOW_RDF_ENABLED=true 설정 후 서비스를 재시작한다. DDL은 자동 커밋이므로 중간 실패 시 객체 상태를 먼저 확인한다. 기존 VK_FLOW 및 원문 데이터는 보존한다. SQLite는 동작 테스트용이며 네이티브 RDF를 제공하지 않는다.

## 에이전트 저장 순서

1. 원문 READY 확인 → 정확한 버전 읽기 → Kev graph_extract 또는 작업 맥락으로 관계 추출 필요성 판단.
2. `knowledge_graph_resolve`로 근거 있는 식별자와 이름 힌트를 구분하고 `knowledge_graph_entities(query, scope)`로 기존 개체를 확인한다. 없으면 `knowledge_graph_entity(entity)`로 명시적 identity_key, label, scope를 저장한다. 이름이 같다는 이유로 자동 병합하지 않는다.
3. `knowledge_graph_search(search={entity_ids:[...],scopes:[...]})`로 기존 관계 확인.
4. `knowledge_graph_assert(assertion)`에 정확한 원문 인용과 확인한 관계를 제출한다. 같은 주어/술어/목적어/조건/기간은 기존 assertion에 근거를 보완하고 recorded 이력 버전을 추가한다. 동일 재요청은 변경하지 않는다.
5. 정정은 `knowledge_graph_history`를 읽고 `knowledge_graph_revise`에 latest expected_version_id 및 전체 수정본을 제출한다. 충돌 시 다시 읽는다. 폐기/복원은 사용자 요청 때만 수행한다.

```json
{
  "scope": "global",
  "subject_id": "<프로젝트 A entity UUID>",
  "predicate": "uses",
  "object_id": "<공통 DB entity UUID>",
  "verified": true,
  "temporal_kind": "INTERVAL",
  "valid_from": "2026-04-01T00:00:00+09:00",
  "temporal_basis": {"text": "2026년 4월 1일부터 프로젝트 A는 공통 DB를 사용한다."},
  "evidence": [{"knowledge_id":"<지식 UUID>","revision_id":"<버전 UUID>","quote":"2026년 4월 1일부터 프로젝트 A는 공통 DB를 사용한다."}]
}
```

위 UUID는 실제 API 반환값으로 바꾼다. 날짜가 없다면 UNKNOWN으로 두고 valid_from/to를 생략한다. TIMELESS도 명시적 근거가 필요하다. user_asserted=true는 사용자가 실제로 말한 기간만 허용한다. 서버는 인용 일치를 검증하지만 자연어 의미나 날짜 해석의 진위는 추출자가 검증해야 한다.

원문별 PENDING → REVIEWING → COMPLETE/FAILED 기록은 [개체 식별·검토 안내](graph-identity-review.md)를 따른다. prepare나 관계 한 건의 저장만으로 검토가 자동 완료되지 않는다.

## 검색과 프로젝트 연결

HTTP는 인증 Bearer 토큰을 사용한다. 공통 경로는 `/api/v1/graph/entities` GET/POST, `/assertions` POST, `/assertions/{id}` PUT, `/assertions/{id}/history` GET, `/search` POST이다. 전체 스키마는 실행 중인 `/docs`에서 확인한다.

```json
{"query":"프로젝트 A","scopes":["global","project:a","project:b"],"valid_at":"2026-05-01T00:00:00+09:00","known_at":"2026-05-10T12:00:00+09:00","depth":1,"max_edges":40}
```

valid_at은 실제 업무 시점, known_at은 당시 저장소가 알고 있던 시점이다. 기간은 [시작, 끝). recorded 이력은 서버가 기록하며 과거로 조작하지 않는다. 업무 날짜를 지정하면 UNKNOWN은 제외된다. include_undated=true로 포함할 수 있다. 각 결과는 근거 title/knowledge_id/revision_id/quote와 적용·기록 기간을 반환한다.

같은 사용자의 프로젝트 A→프로젝트 B 의존, 여러 프로젝트→공통 DB, 서비스→배포 머신 등을 연결할 수 있다. 프로젝트별 개체는 각 scope에 두고 프로젝트 간 관계는 global에 둘 수 있다. 선택한 프로젝트+global 안에 양쪽 개체와 근거가 있어야 관계를 반환한다. scopes를 생략하면 내 전체 범위다. 다른 사용자의 데이터는 접근하지 못한다.

검색은 이름/별칭/identity_key 부분 일치로 시드를 찾고 제한된 관계를 확장한다. 자연어 질의의 개체 인식은 에이전트가 후보를 확인하고 entity_ids를 전달한다. 최대 depth=3, max_edges=100, 단계당 후보500이며 초과 시 truncated=true. 전체 연결성 분석이나 자동 프로젝트 탐색은 아니다. 일반 벡터·키워드 원문 검색은 그대로이고 날짜 필터는 그래프 결과에만 적용한다.

## 노트 화면

상단 ‘관련 그래프’는 검색어에 연결된 공통 그래프를 보여준다. 노트의 ‘연결된 지식’은 그 노트의 근거에서 시작해 연결된 관계를 보여준다. 업무 기준일과 당시 기록 기준은 **브라우저 로컬 시간대**로 입력하고 API 전송 시 UTC로 변환한다. 노트를 열면 현재 시점·해당 노트 범위가 기본이며 ‘조회 조건 변경’에서 바꿀 수 있다. 프로젝트 범위는 쉼표로 복수 입력한다. 비워 두면 기존 검색 범위를 따르며 둘 다 없으면 내 전체 지식이다. 관계 버튼을 누르면 기간과 정확한 원문 버전/인용을 확인한다. 원문 탭은 코드 형식·자동 줄바꿈·사용자 편집을 유지한다.

## 보존과 한계

기존 revision별 VK_FLOW는 삭제하지 않는다. 공통 관계가 없고 날짜를 지정하지 않은 노트에서는 이전 그래프를 표시하며 이전 형식임을 명시한다. 기존 개체를 임의로 공통 병합하지 않는다. 전환할 때는 확인된 매핑 또는 legacy:<knowledge_id>:<node_id> 같은 분리된 키를 사용한다. 전환 시점보다 과거에 알고 있었다고 기록하지 않는다.

원문 새 버전/폐기는 현재 근거를 제외한다. 다른 유효 근거가 있으면 관계를 유지한다. known_at은 SOURCE_ACTIVATED와 폐기/복원 이벤트로 당시 근거를 판단한다. 이 기능 이전의 원문 활성화 이력이 없는 경우, 관계 등록 시 활성 원문 검증을 출발점으로 삼으며 존재하지 않는 과거 이력을 만들어내지 않는다.

관계형 테이블로 소유자·범위·기간 후보를 제한하고 Oracle RDF accessor로 각 assertion version을 검증한다. 같은 트랜잭션으로 기록한다. 임의 SPARQL 실행, 추론 엔진, 대규모 그래프 성능 최적화는 제공하지 않는다. Kev 임계값은 기존 잠정값이며 이번 변경으로 정확도 향상이 검증된 것은 아니다.

선택한 기존 그래프 전환: `./uvw run --no-sync python -m scripts.migrate_workflow_graph <knowledge_id> <revision_id>`. 활성 원문만 허용하고 기존 노드별 분리 키를 사용한다. 중간 실패 시 같은 인자로 재실행할 수 있다. 전환은 관계별 트랜잭션이며 전체 일괄 원자성은 제공하지 않는다. 이름 변경 충돌은 자동으로 덮어쓰지 않는다.
