# 변경 감사와 트랜잭션 outbox

2026-10-18 사용자 승인, 구현 2026-10-19. 기존 원문 revision, 인덱스 history, 공통 RDF version/evidence를 보존한다. API의 의미 있는 작업과 직접 SQL의 행 변경을 함께 관찰한다.

## 계약

- vk_change_context: 서비스 작업명, owner/인증 사용자, request_id, 선언한 머신/edit_origin, 사유, 일시. 서비스 UoW에서 생성하고 같은 트랜잭션의 행 변경에 연결한다. 본문이나 비밀번호는 context에 기록하지 않는다.
- vk_change_event: 대상 테이블/ID, INSERT/UPDATE/DELETE, 변경 전후 JSON snapshot, context ID, DB 사용자, 일시. 원본 FK를 두지 않아 물리 삭제 이후에도 기록을 보존한다. 이벤트 UPDATE/DELETE는 DB 트리거로 거부한다.
- vk_change_outbox: 이벤트당 한 행, PENDING/DONE/FAILED, 시도 횟수, 다음 실행 시각, 안전한 에러 코드. 변경 트리거가 이벤트와 outbox를 같은 트랜잭션에 INSERT한다. 외부 호출/임베딩은 하지 않는다.
- vk_change_review: 직접 SQL 변경 및 원문 갱신에 영향을 받은 RDF 근거 재검토 항목. owner, event_id, target_type/id, reason, OPEN/RESOLVED, 해결 사유/시각. 이벤트+대상+사유 unique로 중복 소비 방지. 검토 완료는 사용자의 확인 기록이며 RDF 사실을 자동 변경하지 않는다.

대상은 vk_item/vk_revision/vk_index/vk_index_entry/vk_g_entity/vk_g_claim/vk_g_version/vk_g_evidence/vk_workflow. 출처는 revision.sources_json이다. 본문·요약·관계 JSON을 포함하되 원본 BLOB·벡터·인증자료·실행 로그는 복제하지 않는다. BLOB의 존재/크기는 기록하며 이 이력만으로 바이너리를 복원할 수 있다고 주장하지 않는다. DB 스키마 DDL 변경은 대상이 아니다. 변경 없는 UPDATE도 SQL이 실행되면 이벤트가 생긴다.

Oracle 트리거는 현재 transaction ID와 owner가 맞는 활성 서비스 context만 참조한다. 서비스는 첫 데이터 변경 전에 context를 등록하고 마지막 flush 후 transaction_id를 NULL로 정리한다. 실패하면 함께 rollback한다. 세션 변수를 사용하지 않아 커넥션 풀에 인증 사용자 정보가 남지 않는다. SQLite는 같은 트랜잭션에서만 보이는 활성 context와 실제 SQLite 트리거로 테스트한다. 직접 SQL은 context가 없으며 애플리케이션 행위자는 UNKNOWN, DB 사용자는 Oracle SESSION_USER로 기록한다. 원본 owner/id의 직접 변경은 거부한다. DB 소유자/관리자가 트리거를 해제할 수 있으므로 변조 불가능한 보안 감사 저장소는 아니다.

후속 worker는 outbox 행 잠금(SKIP LOCKED)과 효과/완료를 같은 트랜잭션으로 처리한다. 실패는 rollback 후 제한적 지수 backoff, 5회 실패 시 FAILED. 프로세스 종료는 DB rollback으로 잠금이 풀려 재시도 가능하다. 원문 활성화 시 현재 요약·참조 RDF를 보완하고 이전 revision을 근거로 쓰는 활성 관계에 재검토를 남긴다. 직접 SQL은 REVIEW 대상으로 표시하고 파괴적 자동 복구/재임베딩은 하지 않는다. API revision의 임베딩은 기존 durable vk_job을 유지해 중복 enqueue하지 않는다. 인덱스 구성원은 현재 revision을 동적으로 참조하므로 별도 본문 캐시 갱신은 없다.

조회 API/MCP: 소유자 범위의 변경 목록·상세(before/after)·재검토 목록, 검토 완료(사유 필수), 실패 outbox 재시도. 일반 삭제는 기존 retire이며 영구 삭제 API/자동 감사 삭제를 추가하지 않는다. 기간별 감사 보존 정책은 별도 운영 결정이다. 과거 이벤트 소급 생성은 하지 않는다.

검증: rollback 원자성, 직접 SQL INSERT/UPDATE/DELETE snapshot, CLOB 한글 장문, append-only/owner 변경 금지, 사용자 경계·삭제 후 이력, context 누수 없음, worker 중복 소비·실패 재시도·RDF 옛 증거 유지, migration, 실제 Oracle 트리거 유효성 및 MCP.

## 검증 결과 (2026-10-19)

- ruff check/format, mypy 44개 파일, pytest 146개 통과.
- 실제 Oracle vk0008 적용 및 트리거 10개 VALID. 한글 장문 CLOB, 직접 SQL, 원자적 rollback, 감사 수정 금지, 사용자 격리, RDF 과거 근거 보존 검증. 검증용 데이터는 rollback.
- 실제 stdio MCP 37개 도구와 신규 변경 목록/상세/재검토 조회 확인.
- 실제 outbox 16개 DONE, 실패 0개 확인. Oracle 세션 시간대와 UTC 바인딩 차이로 발생한 소비 지연은 연결 시 TIME_ZONE=UTC로 해결.
