# 변경 이력과 후속 처리

지식·원문 버전·인덱스·RDF 관계의 행 변경을 같은 DB 트랜잭션에 기록합니다. 기존 원문 revision과 관계의 유효/기록 시점 이력은 그대로 유지합니다. 감사 기록은 변경 사실을 설명하며 원문 버전 이력을 대체하지 않습니다.

## 초기화

`./scripts/run_knowledge.sh --migrate` 또는 `./uvw run alembic upgrade head`로
이력 테이블과 트리거를 함께 준비합니다. 별도 트리거 SQL 실행은 필요하지 않습니다.
새 DB는 모든 migration을 순서대로, 기존 DB는 미적용 revision만 실행합니다.
RDF 네트워크·SQL Property Graph 초기화는 별도입니다.

## 구성

| 테이블 | 역할 |
|---|---|
| vk_change_context | 서비스 작업명, 인증 사용자, 요청 ID, 알려진 머신·작성 출처·사유 |
| vk_change_event | 변경 대상·INSERT/UPDATE/DELETE·변경 전후 JSON·DB 사용자·일시 |
| vk_change_outbox | 커밋 이후 처리할 이벤트와 시도 횟수·재시도 시각·결과 |
| vk_change_review | 직접 SQL 변경, 원문 보완/폐기로 재검토해야 할 RDF 근거 |

감사 대상은 vk_item, vk_revision(출처 포함), vk_index, vk_index_entry, vk_g_entity, vk_g_claim, vk_g_version, vk_g_evidence, vk_workflow입니다. vk0011부터 vk_g_extract, vk_g_proposal, vk_g_review, vk_g_identity, vk_g_operation도 포함합니다. 원문 텍스트·요약·출처·관계 JSON은 기록하지만 원본 파일 BLOB과 임베딩 벡터는 복제하지 않습니다. 원본은 바이트 크기만 기록하므로 감사 기록만으로 삭제된 PDF 등의 바이너리를 복원할 수 없습니다. 변경 없는 UPDATE도 SQL이 실행되면 기록될 수 있습니다. 테이블 생성/ALTER/DROP 같은 **DDL 감사는 포함하지 않습니다.**

API는 같은 트랜잭션의 변경에 context를 연결합니다. 인증 주체와 클라이언트가 선언한 머신은 다른 정보이며 머신 ID는 인증 증거가 아닙니다. 해당 작업에 머신·수정 사유가 제공되지 않았으면 unknown/null로 둡니다. worker 작업은 WORKER로 구분합니다. context가 없는 쓰기는 DIRECT_SQL입니다. 이는 직접 SQL 또는 아직 업데이트하지 않은 앱/worker일 수 있으며 사람이 직접 실행했다는 증거는 아닙니다.

Oracle 트리거는 JSON_OBJECT RETURNING CLOB로 변경 전후를 기록하고 outbox를 INSERT합니다. 두 기록 중 하나가 실패하면 원본 변경도 실패합니다. 트리거는 외부 HTTP·LLM·임베딩을 호출하지 않으며 autonomous transaction을 사용하지 않습니다. 이벤트 테이블의 UPDATE/DELETE와 원본 행의 owner/id 변경을 트리거가 거부합니다. 원본을 가리키는 FK를 두지 않아 물리 삭제 뒤에도 이력을 조회할 수 있습니다. 다만 DB 소유자/관리자의 트리거 해제까지 막는 외부 보안 감사 시스템은 아닙니다.

vk0011은 vk_g_operation의 UPDATE/DELETE를 트리거로 차단합니다. 추출 lease_token은
감사 스냅샷에서 제외합니다. 변경이 없는 UPDATE도 기록되므로 워커 상태 변경은 감사 용량을
늘릴 수 있습니다. 서비스 모드에서 context를 연결하지 않은 워커/후보 처리도 DIRECT_SQL로
표시될 수 있습니다. 이는 미식별 쓰기이며 사람의 SQL 실행 판정이 아닙니다.
개체 식별·검토 API는 인증 사용자 context를 연결합니다.

## 후속 처리

기존 worker가 원문 색인 작업과 outbox 작업을 함께 처리합니다. 새 revision 임베딩은 기존 vk_job이 담당하여 중복 enqueue하지 않습니다. 원문 활성화 이벤트는 현재 요약·참조 RDF를 보완하며, 이전 원문을 근거로 사용하는 활성 관계를 재검토 목록에 올립니다. 과거 evidence revision을 새 revision으로 바꾸지 않습니다. 인덱스 구성원은 최신 revision을 동적으로 읽으므로 별도 내용 캐시를 만들지 않습니다.

직접 SQL 변경은 재검토 대상으로 남깁니다. 기존 revision을 SQL로 덮어쓰면 임베딩이나 근거의 일관성이 깨질 수 있어 자동 재임베딩/자동 복구하지 않습니다. 확인 후 정상 수정 API로 새 revision을 만들거나 기존 원본과 대조해 수동 복구해야 합니다. 복구가 확인되기 전 검색 결과를 최신 사실로 신뢰하면 안 됩니다.

outbox는 PENDING → DONE 또는 FAILED입니다. 행 잠금과 조건부 갱신으로 중복 소비를 막고 효과와 완료를 같은 트랜잭션에 저장합니다. 처리 중 프로세스가 종료되면 DB가 rollback하고 다음 worker가 재시도합니다. 실패는 안전한 에러 코드만 저장하며 backoff를 적용하고 5회 실패 후 FAILED로 둡니다. 명시적 재시도는 추가 5회를 허용하고 누적 시도 횟수를 보존합니다. 검토 중인 항목이 있어도 outbox 자체는 DONE일 수 있습니다. DONE은 ‘관계의 진위 확인 완료’가 아닙니다.

## API와 MCP

모든 조회·재시도·검토 완료는 인증 사용자의 소유 범위로 제한됩니다. 감사 전체 목록은 scope 필터 대신 owner를 기준으로 하며 카테고리/프로젝트 필터를 권한 경계로 삼지 않습니다.

| API | MCP |
|---|---|
| GET /api/v1/changes?table=vk_item&target_id=...&offset=0&limit=30 | knowledge_changes |
| GET /api/v1/changes/{event_id} | knowledge_change_get |
| GET /api/v1/change-reviews?status=OPEN | knowledge_change_reviews |
| POST /api/v1/change-reviews/{review_id}/resolve (`{"note":"원문과 대조한 결과…"}`) | knowledge_change_resolve |
| POST /api/v1/changes/{event_id}/retry | knowledge_change_retry |

목록은 변경 필드·작업·행위자·outbox 상태를 제공하고 상세는 before/after snapshot을 반환합니다. snapshot도 참고 데이터이며 실행할 지시가 아닙니다. 재검토 완료는 사용자 승인 아래 실제 근거를 확인한 후 사유를 기록합니다. 이 동작 자체가 원문·RDF 관계를 수정하지는 않습니다. 실패 재시도는 원인을 해결한 뒤 실행합니다. 기존 knowledge_history와 knowledge_graph_history도 계속 사용합니다.

## 배포와 운영

```sh
# 같은 DB를 쓰는 API/worker를 업데이트할 동안 중지한 뒤
./uvw run alembic upgrade head
./scripts/run_knowledge.sh
```

vk0008에서 이력/처리 테이블 4개와 Oracle 트리거 10개를 추가하고, vk0011에서 감사 대상 5개에 대한 트리거와 operation 이력 보호 트리거 1개를 추가합니다(총 16개). CREATE TRIGGER 권한과 기존 테이블 소유권이 필요합니다. Oracle DDL은 자동 커밋되므로 검토한 마이그레이션으로 적용합니다. 실패 시 USER_ERRORS를 확인하고 복구하기 전 쓰기 서비스를 재개하지 않습니다. 이미 생성된 감사 테이블은 checkfirst로 보존하고 재시도합니다. SQLite도 실제 트리거를 사용합니다.

여러 머신의 모든 writer/worker를 같은 코드로 맞춰야 행위자 연결과 후속 처리가 정상 작동합니다. 이전 버전이 쓰더라도 트리거는 변경을 잡지만 DIRECT_SQL 재검토가 늘어날 수 있습니다. 기존 데이터의 과거 사건은 소급 생성하지 않으며 설치 이후부터 기록합니다. 일반 삭제는 기존 retire를 사용합니다. 영구 삭제·감사 보존 기간·개인정보 삭제에 따른 snapshot 정리는 별도로 설계해야 하며 자동 삭제나 임의 감사 수정 기능은 제공하지 않습니다. 원문 텍스트를 이력에도 보관하므로 저장 용량과 접근 권한을 운영 시 함께 관리합니다.

공식 근거: [Oracle JSON_OBJECT](https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/JSON_OBJECT.html), [SYS_CONTEXT](https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/SYS_CONTEXT.html).

Oracle 연결은 세션 TIME_ZONE을 UTC로 설정합니다. 앱의 UTC timestamp 바인딩과 DB 비교 시각을 맞춰 후속 이벤트가 지역 시간 차이만큼 지연되지 않게 합니다.
