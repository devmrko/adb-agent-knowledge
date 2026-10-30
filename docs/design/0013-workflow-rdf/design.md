# 업무 흐름 RDF와 Kev 라우팅 제안

> 설계 당시의 결정·계획을 보존한 기록입니다. 현재 기본값·설치·지원 범위는 [현재 매뉴얼](../../README.md)을 기준으로 확인하세요. 이 문서의 계획이나 과거 검증은 현재 구현·배포 보장이 아닙니다.

2026-10-16 사용자 제안에 대한 검토. **1차 연동 구현 완료: 버전별 관계 저장 및 MCP 조건부 조회**. 사용자가 알려준 DB Companion에 네이티브 RDF 기반 구현이 있어 이를 재사용 대상으로 확인했다. 현재 ADB 계정에서 API/권한과 전용 네트워크 생성, 한국어 트리플 저장·조회·롤백을 확인했다. 무제한 경로 탐색과 관계 자동 생성기는 범위 밖이다.

초기 검토 내용은 아래와 같으며, 실제 제공 범위는 마지막 **1차 구현 계약**을 따른다.

## 목적과 저장

원문 및 벡터·키워드 검색은 유지한다. 업무 흐름이 명시된 지식에 한해 RDF를 추가적인 조회 표현으로 만든다. RDF 트리플(주어, 관계, 목적어)에 named graph를 더한 쿼드로 지식/버전을 식별한다. 단순 SQL 세 열 테이블을 RDF 지원으로 부르지 않는다.

예: 접수 hasStep 검토; 검토 nextStep 승인; 승인 requires 역할관리자. 분기 조건은 전이 노드(transition)의 fromStep/toStep/condition으로 표현해 어떤 간선에 붙은 조건인지 분명히 한다. 트리플 삽입 순서는 업무 순서가 아니다. 반복 흐름도 가능하므로 무조건 DAG로 가정하지 않는다.

원문이 기준이다. 관계마다 knowledge_id/revision_id와 근거 위치를 연결한다. 머신/출처는 기존 provenance를 재사용한다. 이름이 같다는 이유로 서로 다른 프로젝트 단계/역할을 합치지 않는다. 안정적인 URI와 버전별 named graph를 사용한다.

## Kev의 두 판단

저장: 기존 save 판단 후, 확정된 저장 내용에 명시적 순서·분기·의존 관계가 있는지 graph_extract를 판단한다. Kev는 점수를 내므로 트리플 생성기는 아니다. 에이전트/별도 추출기가 허용된 어휘와 원문 근거에 맞춰 구조화하고 서버가 검증한다. 내용에 없는 관계를 확정 사실로 저장하지 않는다.

조회: 기존 lookup 후, 순서·담당·조건·선후 의존성 질문이면 graph_lookup 판단을 추가한다. 벡터·키워드로 관련 원문 후보를 찾고 그 후보의 허용된 활성 그래프에서 관계를 확장한다. 명시적 흐름 조회는 낮은 점수여도 조회한다. agent_review/장애는 에이전트 판단과 기존 검색으로 대체하고 그래프 미조회 사실을 표시한다. 기존 0.2 기준을 새 판단에 그대로 적용하지 않는다.

## 소유권과 버전

인증된 owner + scope + ACTIVE 원문 revision으로 서버가 그래프 집합을 제한한다. named graph 이름만으로 권한이 보장되지 않는다. 모델이 임의 SPARQL/그래프 URI를 실행하게 하지 않고 허용된 조회 템플릿과 바인딩을 쓴다. 탐색 깊이/시간/결과 수를 제한한다. 폐기하거나 이전 버전인 그래프는 기본 조회 대상이 아니다.

원문 저장과 그래프 작업을 별도 상태로 추적한다. 원문 재색인과 RDF 구축은 실패/재시도 가능해야 한다. 그래프 완성 뒤 해당 revision만 공개한다. 새 원문이 활성화됐는데 새 그래프가 준비되지 않았다면 구버전 그래프를 섞지 않고 graph_pending으로 원문만 반환한다. 사용자 편집도 새 그래프를 구축하며 과거 이력은 보존한다. 업무를 실행하는 엔진은 범위 밖이다.

## 구현 순서와 검증

1. 실제 ADB 버전, SEM_APIS/SEM_MATCH 및 schema-private network 권한을 읽기 전용으로 점검한다. 작은 전용 그래프에서 삽입/조회/롤백 검증 후 지원을 주장한다.
2. 업무 흐름 30개 이상과 일반 메모 음성 사례로 graph_extract/graph_lookup 라우팅 평가. 관계 정확도, 근거 보존, 조회 누락, 총 지연시간을 따로 측정한다.
3. opt-in RDF 저장/조회와 버전 연동. 그래프 미준비/실패, 타 사용자·프로젝트 누출, 분기·순환·편집·폐기 테스트.
4. 검색 결과에는 근거 원문 및 관계를 함께 제공한다. 전후 검색 품질/비용을 평가한 뒤 자동 적용 범위를 넓힌다.

## 공식 근거

- https://www.oracle.com/europe/database/integrated-graph-database/graph-faq/ : Autonomous의 RDF/SPARQL 지원 설명.
- https://docs.oracle.com/en/database/oracle/oracle-database/26/rdfrm/rdf-data-database.html : RDF network, schema-private network, triples/quads와 named graphs. 네트워크는 명시적으로 생성해야 한다.

공식 지원 설명은 현재 연결 계정의 설정/권한 또는 성능 검증을 대신하지 않는다.


## 기존 DB Companion 구현 확인 — 2026-10-16 보충

사용자 정정에 따라 `<workspace>/db-companion`의 소스를 읽었다(확인 시 HEAD `a98b00e`). DB Companion 자체와 실제 DB는 수정하지 않았다. 아래는 소스 확인 결과이며 이번에 실제 DB 실행을 재검증한 것은 아니다.

- `src/main/java/com/dbcompanion/repository/NativeRdfRepository.java`: 네트워크/모델 확인 및 생성, SDO_RDF_TRIPLE_S 바인드 일괄 삽입, named graph 읽기, 시간·결과·term 크기 제한.
- `src/main/java/com/dbcompanion/common/db/RdfQuerySql.java`: DBC_RDF/DBC_QUERY, UUID로 제한한 graph URI, SEM_MATCH CONSTRUCT 조회. 임의 사용자 SPARQL을 실행하지 않는다. SEM_MATCH 구문/소유자 리터럴 제약도 주석에 명시됨.
- `src/main/java/com/dbcompanion/service/QueryArchiveRdf.java`: RDF4J 파싱 및 N-Triples 직렬화, 크기 검사, 정렬된 해시 및 모델 동등성 검증. 근거로 선택된 관계를 RDF로 표현한다.
- `src/main/java/com/dbcompanion/repository/NativeMetadataRepository.java`: PUBLIC SEM_APIS synonym을 실제 package와 연결하여 기능을 확인한다. 고정 MDSYS.SEM_APIS 패키지만 검사하는 구현보다 이 탐지 방식을 우선 참고한다.
- `src/main/resources/sql/ontology-native/{setup,capture,read,read-columns}.sql`: schema-private network 생성, 스냅샷 저장·조회. read.sql에 SEM_MATCH의 DB JVM 의존/ORA-29538 안내, read-columns.sql에는 기본 SQL RDF accessor 조회 대안이 있다. columns()는 read.sql을 호출하므로 SQL 대안이 자동 fallback으로 연결된 것으로 간주하지 않는다.
- 조사한 src/main에서 Kev/systemone 연결은 찾지 못했다. 업무 단계·분기 온톨로지와 Kev 판단은 이 프로젝트에 추가해야 한다.

따라서 네이티브 RDF 저장·조회 기반을 처음부터 재설계하지 않는다. 기존 SQL 패턴·검증 규칙을 Python 저장소 계층으로 옮기고, 기존 DBC_* 네트워크를 건드리지 않는 전용 namespace, owner/scope/revision 제한, 업무 흐름 관계 및 Kev graph_extract/graph_lookup을 추가한다. Java 클래스/RDF4J 의존성을 Python으로 그대로 복사하는 방식은 아니다. 기존 구현의 일반 SQL 조회 대안은 제한된 RDF 조회이며 임의 SPARQL/경로 탐색의 대체재로 주장하지 않는다.

## 1차 구현 계약

승인된 구현: 별도 불변 Workflow manifest를 READY 원문 revision에 붙인다. PUT /knowledge/{id}/revisions/{revision}/workflow는 owner/ACTIVE/현재 원문/최신 revision을 잠금 후 검사한다. 같은 payload 재요청은 멱등, 다른 내용으로 덮어쓰기는 409이며 원문 새 revision이 필요하다. GET은 활성 revision만 반환한다. 새 원문이 READY로 활성화되면 구버전 그래프를 제외하며 새 workflow가 없으면 ABSENT로 반환한다.

DTO는 nodes(id,label), edges(source,target,relation,condition,evidence)와 verified=true. 라벨과 evidence는 원문에 존재해야 하고 참조/크기/중복을 검사한다. 의미가 실제로 근거에서 도출되는지는 추출 에이전트가 확인한다. Kev는 그래프 생성기가 아니다. 원문 저장 후 응답의 graph_extract 판단에 따라 READY 확인 후 knowledge_set_workflow를 호출한다. 파일/URL의 추출된 내용은 에이전트가 읽고 별도로 판단한다.

네트워크 VK_FLOW_RDF / 모델 VK_FLOW, named graph에 owner hash와 revision UUID. Oracle SDO_RDF_TRIPLE_S로 바인드 일괄 삽입, 기본 조회는 DB Companion read-columns와 같은 accessor SQL로 범위 제한한다(JVM 불필요). 구조화된 관계를 반환하며 임의 SPARQL과 무제한 경로 탐색은 제공하지 않는다. manifest와 RDF가 한 트랜잭션에서 커밋되므로 실패 시 둘 다 남지 않는다. 원문/벡터 저장은 독립적이다. SQLite는 manifest 기반 테스트 대체이며 네이티브 RDF로 주장하지 않는다.

MCP search의 graph_mode=auto/always/never. auto는 Kev graph_lookup 판단 후 후보 중 현재 revision의 그래프를 함께 읽는다. 장애/agent_review는 흐름 질의 단어와 작업 맥락으로 보수적으로 판단하고 결과에 decision/status를 노출한다. 일반 벡터 검색 실패를 그래프로 숨기지 않는다. save/revise 응답에 별도 graph_extract 판단을 제공한다. lookup과 extract의 기준은 별도 잠정 설정으로 평가 전이다. 명시적 workflow 도구는 판단을 우회한다.
