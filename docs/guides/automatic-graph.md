# 자동 그래프 추출과 검토

새로 활성화된 원문을 독립 워커가 찾아 `operations-v1` 모델로 개체·관계를 추출한다. 기존 미처리 활성 원문도 순차 처리한다. 일반 메모는 Kev가 실행 여부를 결정하고, 명시적 추출 요청·PROCEDURE·TROUBLESHOOTING·기존 관계 근거의 수정은 건너뛰지 않는다. Kev가 실패하면 추출을 진행한다. 분류 모델은 관계 자체를 생성하지 않는다.

## 설정과 실행

```dotenv
GRAPH_AUTO_ENABLED=true
GRAPH_AUTO_URL=https://openrouter.ai/api/v1
GRAPH_AUTO_MODEL=qwen/qwen3.5-flash-02-23
GRAPH_AUTO_ALLOW_REMOTE=true
OPENROUTER_API_KEY=사용자가_로컬에_입력
GRAPH_AUTO_POLICY=review
GRAPH_AUTO_MAX_CHARS=24000
```

외부 LLM 사용은 해당 제공자에 원문과 제한된 기존 개체 후보를 전송한다. OpenRouter는 data_collection=deny와 require_parameters=true를 사용한다. 명시적으로 다른 endpoint를 선택하면 GRAPH_AUTO_API_KEY로 별도 키를 지정할 수 있다. `.env`와 키는 Git에 포함하지 않는다. 로컬 OpenAI 호환 서버는 loopback URL, 해당 model, allow_remote=false로 구성한다.

서비스를 중지하고 `./uvw run --no-sync alembic upgrade head`로 vk0009를 적용한 뒤 `./scripts/run_knowledge.sh`를 실행한다. 이 실행기는 API, 임베딩/outbox 워커, 그래프 추출 워커를 함께 관리한다. 분리 실행은 `./.venv/bin/python -m knowledge_app.graph_auto_worker` 또는 `--once`를 사용한다.

2026-10-19 OpenRouter 공개 모델 목록 기준 Qwen3.5-Flash는 입력 100만 토큰당 $0.065, 출력 $0.26이다. 가상 한국어 운영 기록에서 6개 개체/5개 명시적 관계를 약 4.6초에 추출했으나, 이 한 사례가 일반 정확도를 입증하지 않는다. 실제 프로젝트 자료로 정확도·비용 평가가 필요하다.

## 두 가지 정책

- review: 모든 추출 관계를 후보로 보관한다. 노트 화면의 ‘지식 연결’ 또는 MCP에서 정확한 원문과 개체 식별을 확인한 뒤 승인한다.
- auto_existing: 기존 개체의 고유 identity_key가 원문에 `service:orders --uses--> db:orders` 형태로 관계와 함께 정확히 명시된 경우만 자동 승인한다. 원문의 인증 작성자 이력을 확인할 수 있어야 한다. 자연어 관계, 신규 개체, 조건 있는 관계, 이름만 같은 개체는 여전히 검토 대상이다. 모델이 높은 자신감을 표시한다는 이유로 자동 승인하지 않는다.

신규 개체는 검토자가 확인한 고유 식별키를 입력한다. 이미 있으면 기존 ID를 선택한다. 새 문서에 같은 라벨이 있다는 이유로 기존 개체를 병합하지 않는다. 동일 관계는 기존 GraphService의 assertion signature에 따라 근거를 추가한다. 자동/수동 승인 모두 정확한 원문 버전을 참조한다. 업무 날짜는 임의 추정하지 않고 UNKNOWN으로 남기며 필요 시 기존 관계 수정 도구로 보완한다.

## 상태와 복구

`vk_g_extract`: owner+원문 revision+schema version+model별 유일한 작업. PENDING/RUNNING/DONE/SKIPPED/STALE/FAILED와 시도 횟수, lease, 안전한 오류 코드를 기록한다. HTTP 호출은 DB 잠금 밖에서 수행한다. 5분 임대가 만료되면 재처리할 수 있고 오래된 임대의 결과는 버린다. 실패 5회 후 FAILED, 명시적 재시도는 누적 시도 횟수를 유지하고 추가 5회를 허용한다.

`vk_g_proposal`: 정확한 원문 인용, 주체/대상 후보, 모델 작업 ID, 승인/기각 결과와 사유를 보관한다. 후보는 확정 그래프 검색에 노출하지 않는다. DONE은 추출 완료이며 모든 관계가 승인되었다는 의미가 아니다. 같은 검토 재요청은 멱등이며 다른 재검토는 거부한다. 승인 시 원문 잠금과 현재 버전을 재검증하고 개체·RDF 관계·후보 결과를 한 트랜잭션으로 반영한다. 이후 근거 변경은 기존 변경 이벤트 재검토 절차를 따른다.

현재 원문이 바뀌거나 폐기되면 미승인 후보는 STALE로 표시하며 승인할 수 없다. 추출 중 바뀐 원문 결과도 STALE로 종료한다. 새 원문에서 언급이 사라졌다고 과거 관계를 자동 삭제하지 않는다.

## API와 MCP

| 동작 | HTTP | MCP |
|---|---|---|
| 모델/정책 확인 | GET /api/v1/graph/extraction/schema | knowledge_graph_extraction_schema |
| 작업 목록 | GET /api/v1/graph/extraction/runs | knowledge_graph_extraction_runs |
| 현재 원문 추출 | POST /api/v1/graph/extraction/knowledge/{id} | knowledge_graph_extract |
| 실패 작업 재시도 | POST /api/v1/graph/extraction/runs/{id}/retry | HTTP |
| 후보 목록 | GET /api/v1/graph/proposals | knowledge_graph_proposals |
| 승인/기각 | POST /api/v1/graph/proposals/{id}/review | knowledge_graph_proposal_review |

목록은 knowledge_id 필터, offset/limit/next_offset을 제공한다. 모든 데이터는 인증 소유자 범위로 제한한다. approve는 주체·대상에 각각 `{existing_id}` 또는 `{identity_key}`를 요구한다. reject에는 사유만 필요하다. UI의 ‘전체 연결’, ‘선택한 노트 연결’, ‘선택한 노트 추출’에서 접근한다.

## 현재 한계

- 공통 모델은 코드에 버전 고정되어 있다. 동적 온톨로지 편집/승인, 모델 확장 후보, 자동 주제 요약은 이번 배포에 포함하지 않는다.
- 자연어의 진위·인과·동일성은 JSON 구조 검증만으로 증명되지 않는다. 제한된 자동 반영 외에는 검토가 필요하다.
- 한 원문이 설정 문자 한도를 넘으면 SOURCE_TOO_LONG으로 명확히 실패한다. 조용히 잘라 처리하지 않는다. 장문 분할·문서 간 추론은 후속 과제다.
- 기존 개체 제안은 같은 scope/global의 최대 501개를 살펴 원문에 이름/식별키가 있는 최대 100개를 사용한다. 전체 개체 탐색이나 의미 기반 자동 병합을 보장하지 않는다.
- 후보/작업 테이블 자체에 범용 행 감사 트리거는 아직 없다. API의 불변 검토 결과와 기존 개체/관계 감사 이력을 사용한다. DB 관리자의 직접 수정 방지 감사는 별도 확장이 필요하다.

참고: [Neo4j KG Builder](https://neo4j.com/docs/neo4j-graphrag-python/current/user_guide_kg_builder.html), [Graphiti](https://github.com/getzep/graphiti), [OpenRouter 모델 목록](https://openrouter.ai/api/v1/models).

PARTIAL은 일부 관계가 미선언 끝점/자기 관계/모델 규칙 위반으로 제외됐음을 뜻한다. 처리 내역의 제외 수를 확인한다. 유효 관계만 후보로 남기고, 정확한 원문 인용이나 끝점 식별 검증에 실패한 관계 역시 제외 건수에 포함하고 저장하지 않는다. 검증된 나머지 관계는 보존한다. 동일 추출 내부에서 key 대신 유일한 label이 사용된 경우만 정규화하며 DB의 동일 이름 개체를 병합하는 기능은 아니다.

## 프로젝트 중심 추출 v2

프로젝트 영역(project_area), 소프트웨어 구성 요소(component), 템플릿(template)을 구분합니다.
예: Cafesto UX → part_of → Cafesto → created_from → TypeScript Foundation.
created_from은 생성 계보이며 현재 의존(depends_on)이나 업데이트 전파를 뜻하지 않습니다.
영역 이름은 프로젝트를 포함하고, 원문에 소속 근거가 있어야 합니다. 기존 대상 ID는
명확할 때만 재사용합니다. 같은 이름만으로 대상을 자동 병합하지 않습니다.
추출 후 별도 모델 호출로 관계 의미를 검토합니다. 불확실/미지원 관계는 후보에서 제외합니다.
이 검토는 정확성 보증이 아니며 자연어 후보는 여전히 승인 전 사실이 아닙니다.
이전 PENDING 후보는 LEGACY로 표시되며 새 기준으로 재추출해야 승인할 수 있습니다.
승인된 기존 관계와 이력은 유지됩니다. v2는 새로운 작업 키를 사용하므로 기존 활성
지식도 재추출하며 공급자 호출 비용이 발생합니다.

## 자동 연결 후 수정

`GRAPH_AUTO_POLICY=auto_verified`는 의미 검토를 통과한 관계를 자동으로 반영합니다.
새 대상은 자동 식별키로 생성하며 기존 대상은 검증된 ID를 재사용합니다. 동명 대상이나
식별 불확실성, 원문 변경, 반영 오류는 보류합니다. 자동 연결은 추론 결과이며 오류가
있을 수 있습니다. 화면의 지식 연결에서 연결 수정/연결 해제로 사용자가 조정합니다.
수정에는 최신 버전 충돌 검사를 적용하고 이전 이력·근거를 보존합니다. 사용자가
수정한 관계의 이전 후보는 같은 원문 항목에서 자동으로 다시 반영하지 않습니다.
기존 v2 완료 작업의 미승인 후보도 한 번 자동 반영을 시도합니다. 사람이 확정했다고
표시하지 않으며 `AUTO: auto_verified` 사유를 남깁니다. 기본 review와 명시적 ID
삼중항만 자동 반영하는 auto_existing 정책도 유지됩니다.
