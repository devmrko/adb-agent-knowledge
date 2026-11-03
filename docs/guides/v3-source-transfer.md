# v3 원문 이관·검증·전환 / Source transfer

v3의 **기존 데이터 이관 도구**입니다. 신규 저장·수정·주 검색을 포함한 현재 구성은
[v3 주 저장소 안내](v3-primary-store.md)를 참조하세요. 기존 설치의 기본값은 legacy입니다.

## 바뀐 경로

```text
READY 원문 버전 → vk_source_transfer QUEUED
  → 작업자가 임대 토큰 확보(PROCESSING)
  → 별도 Agent Memory store에 버전별 JSON·청크 벡터 저장
  → 원문 해시 + 정확한 청크 + 벡터 차원/유한값/영벡터 검사(VERIFIED)
  → 운영자가 generation 확인 후 activate(ACTIVE)
  → 원문 API·MCP·웹 읽기 / 그래프 인용 검증에 SDK 원문 사용
```

- 작업 상태는 DB에 남습니다. 프로세스를 재시작해도 상태를 확인하고 이어갈 수 있습니다.
- 작업자가 사라지면 15분 임대 만료 후 다른 작업자가 가져갑니다. 이전 토큰으로 완료할 수 없습니다.
- 실패는 FAILED로 남고 명시적으로 retry합니다. SDK 저장 후 응답이 불확실해도 같은 ID로 기존 내용을 비교합니다.
- 부분 색인이 손상된 경우 자동 덮어쓰기/복구하지 않습니다. 검증 실패로 남겨 운영자 확인을 요구합니다.
- ACTIVE 원문이 SDK에 없거나 해시가 다르면 오류를 반환합니다. 자동으로 옛 본문을 대신 반환하지 않습니다.
- rollback은 보존된 기존 원문 해시를 확인하고 VERIFIED로 되돌립니다. SDK 장애 중에도 가능합니다.
- activate/rollback/retry는 generation으로 경합을 검사하고 vk_event에 기록합니다.
- 이관 대상은 소유자+지식 ID+원문 버전 ID입니다. 이전 원문과 파일 바이트는 삭제하지 않습니다.

## 설정과 운영 명령

이 명령은 **DB 접속 권한이 있는 신뢰된 서버 운영자용**입니다. 공개 HTTP/MCP 관리 도구가 아닙니다.
`--issuer`, `--subject`에는 원문을 만든 인증 주체의 정확한 값을 사용합니다. 웹 사용자는
WEB_ACTOR_ISSUER/WEB_ACTOR_SUBJECT, 토큰 사용자는 검증된 토큰의 issuer/subject입니다.
임의 별칭이나 해시 owner_id를 subject로 넣지 않습니다. 이 CLI를 일반 사용자에게 제공하지 마세요.

`.env`에 기존 접속/임베딩 설정과 `KNOWLEDGE_V3_STORE_ID=AKKNOWLEDGEV3`를 둡니다.
기존 AGENT_MEMORY_STORE_ID와 달라야 합니다. 임베딩 프로필을 이관 도중 바꾸지 않습니다.

```sh
./uvw sync --extra agent-memory
./.venv/bin/alembic upgrade head
# SDK 저장소는 별도 초기화. --migrate가 대신 만들지 않습니다.
./.venv/bin/python -m scripts.source_transfer init
./.venv/bin/python -m scripts.source_transfer enqueue \
  --issuer 'exact-issuer' --subject 'exact-subject' \
  --knowledge-id 'knowledge-uuid' --revision-id 'revision-uuid'
./.venv/bin/python -m scripts.source_transfer process --max-jobs 10
./.venv/bin/python -m scripts.source_transfer status \
  --issuer 'exact-issuer' --subject 'exact-subject' --revision-id 'revision-uuid'
# status의 VERIFIED와 최신 generation 확인. 아래 3은 예시입니다.
./.venv/bin/python -m scripts.source_transfer activate \
  --issuer 'exact-issuer' --subject 'exact-subject' --revision-id 'revision-uuid' --generation 3
```

`process`는 한 번 실행 후 종료하며 최대 지정 건수만 처리합니다. 반복 실행하거나 운영자가 스케줄러에
등록할 수 있습니다. 출력의 processed는 시도한 건수이며 성공/활성화 건수가 아닙니다.
이관 작업 상태를 반드시 확인합니다. 자동 대량 enqueue와 자동 ACTIVE 전환은 제공하지 않습니다.

API의 `.env`에서 `KNOWLEDGE_SOURCE_BACKEND=v3`로 설정하고 API를 재시작해야
ACTIVE 버전에 SDK 원문 조회가 적용됩니다. 미이관/VERIFIED 버전은 기존 경로를 사용합니다.
기본 legacy에서는 manifest를 조회하지 않습니다. SDK store/schema가 준비되지 않은 상태에서 켜지 마세요.

복구는 먼저 status로 최신 generation을 얻고 다음과 같이 수행합니다.

```sh
./.venv/bin/python -m scripts.source_transfer rollback \
  --issuer 'exact-issuer' --subject 'exact-subject' --revision-id 'revision-uuid' --generation 4
# FAILED 작업만 retry 가능. status의 실제 generation으로 교체합니다.
./.venv/bin/python -m scripts.source_transfer retry \
  --issuer 'exact-issuer' --subject 'exact-subject' --revision-id 'revision-uuid' --generation 3
```

전체 설정을 legacy로 되돌리면 모든 원문을 기존 경로에서 읽지만, 이는 개별 rollback 이력을
만들지 않는 구성 변경입니다. 관리 가능한 복구에는 버전별 rollback을 사용하세요.

## v3 주 경로와의 관계

vk0016 이상에서 API/워커를 v3로 함께 실행하면 신규 저장·수정과 주 벡터/키워드 검색도 SDK를 사용합니다.
이 CLI는 기존 자료의 명시적 이관·복구용입니다. 기존 원문/벡터는 복구와 관계형 기능 호환을 위해 유지하며,
첨부 BLOB·도메인 이력·그래프 기준 테이블도 삭제하지 않습니다. 상세한 기능별 역할·전환·복구는
[v3 주 저장소 안내](v3-primary-store.md)에 있습니다.

## 격리 검증

```sh
./.venv/bin/python -m scripts.smoke_source_transfer \
  --env-file /path/to/isolated-test.env \
  --hf-home /path/to/cached/huggingface \
  --output .run/v3-transfer/result.json
```

VKV_/OAM_TEST_ 테스트 계정만 허용합니다. 최신 migration을 적용하고 V3TRANSFER1103 store와
새 시험 소유자 아래 합성 문서를 만듭니다. 사전에 테스트 RDF·Property Graph를 준비하세요.
기존 한국어 모델의 고정 revision 캐시가 필요합니다. 자료를 자동 삭제하지 않습니다.
결과는 [검증 기록](../reference/v3-transfer-validation.json)에 별도로 보존합니다.

## English summary

This CLI migrates existing source versions with durable leases, integrity checks and explicit activation/rollback.
Use it as a trusted DB operator with exact authenticated issuer/subject, not a public user endpoint.
Current v3 (vk0016+) also handles new writes/revisions and main retrieval automatically through SDK storage.
See the [current primary-store guide](v3-primary-store.en.md) for setup, identity, history and rollback.
The results linked above describe the earlier isolated transfer test, not the full production cutover.
