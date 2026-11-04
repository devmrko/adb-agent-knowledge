# v3: Agent Memory를 원문·검색의 주 저장소로 사용

[English](v3-primary-store.en.md)

v0.3.0-alpha.1은 업무 지식의 **원문과 검색 벡터를 Oracle Agent Memory에 저장**하고,
기존 API/MCP의 저장·수정·검색·이력·그래프 기능을 유지합니다. Agent Memory만 설치하면
업무 버전·감사가 저절로 생기는 구조는 아닙니다. 아래 역할을 함께 운영합니다.

| 기능 | v3 담당 |
|---|---|
| 요약·상세·출처를 포함한 원문 JSON | 별도 SDK store의 `<store>_MEMORY.CONTENT` |
| 검색 청크·벡터 | `<store>_RECORD_CHUNKS` |
| 벡터+키워드 검색 | SDK 벡터/텍스트를 Oracle SQL로 조회하고 기존 RRF/리랭커 적용 |
| 지식 ID·현재 버전·분류·권한·범위 | 기존 vk_item/vk_revision |
| 수정 이력·감사·폐기/복원·충돌 방지 | 기존 버전·이벤트·트리거·작업 테이블 |
| 첨부 원본 파일·추출 메타데이터 | 기존 원문 버전의 BLOB 및 필드 |
| 인덱스·원본 위치·머신 정보 | 기존 ID와 출처 필드 유지, 원문 JSON에도 출처 보존 |
| RDF·Property Graph·근거·시점 조회 | 기존 vk_g_* 및 네이티브 RDF/Property Graph 유지 |
| 에이전트 경험·기억 간 관계 | 기존 별도 AGENT_MEMORY_STORE_ID (기본 AKMEMORY) 유지 |
| Kev·사용자 원칙·훅 | 기존 기능 유지 |

기존 vk_revision 본문과 vk_chunk는 복구 사본 및 관계형 호환 자료로 보존합니다. 일부 근거 검토·감사
처리는 이 일치하는 사본을 사용합니다. **이 테이블들을 지우는 전환이 아닙니다.** 원문·검색의 주 경로를
바꾸고, 도메인 이력과 그래프를 기존 ID로 연결하는 전환입니다. 직접 SQL 본문 수정은 SDK 색인·이력을
같이 갱신하지 않으므로 지원 MCP/API로 수정하세요. SDK 기억 관계를 업무 관계로 일괄 치환하지 않습니다.

## ID와 수정 이력

```text
knowledge_id K1                같은 지식은 계속 K1
 ├─ revision_id R1 ─→ SDK record_id hash(owner, K1, R1)
 └─ revision_id R2 ─→ SDK record_id hash(owner, K1, R2)

RDF 근거: K1/R1 + 정확한 인용  (수정해도 R2로 몰래 바꾸지 않음)
현재 버전: R2                 (새 SDK 원문·색인 검증 완료 후 변경)
```

기존 knowledge_id/revision_id/owner_id와 그래프 ID를 재발급하지 않습니다.
SDK USER_ID는 기존 인증 소유자이고, RECORD_ID는 owner/knowledge/revision JSON 배열의 SHA-256입니다.
`vk_source_transfer.sdk_record_id`가 이 연결을 명시적으로 보관합니다. 이름·제목은 식별키가 아닙니다.
없는 agent_id/thread_id를 임의로 만들지 않습니다. 세션/에이전트 출처와 지식 소유권은 구분합니다.
웹 ‘출처와 버전’ 및 ‘이 항목 SQL’에서 SDK store/record ID와 기존 지식·버전 ID를 확인할 수 있습니다.

## 저장·조회 흐름

1. MCP/API가 기존 지식/버전/작업 ID를 만들고 QUEUED를 반환합니다.
2. 워커가 원문을 추출하고 설정된 임베딩을 계산합니다.
3. SDK에 버전별 JSON·청크·벡터를 기록하고 해시·청크·벡터 구조를 검증합니다.
4. 검증 후 같은 RDB 트랜잭션에서 ACTIVE 이관 상태, 현재 원문 버전, READY 및 이력을 공개합니다.
5. 실패하면 FAILED이며 이전 활성 버전은 유지됩니다. 재시도는 동일 SDK ID를 확인·재사용합니다.
6. 검색은 SDK 청크/벡터를 기존 ID·위치와 조인하고 **사용자·현재 버전·범위·상태 필터 후** 후보를 제한합니다.
7. 검색 결과의 원문 ID로 SDK 본문과 기존 RDF/Property Graph 근거를 조회합니다.

SDK 쓰기와 RDB 공개는 하나의 분산 트랜잭션이 아닙니다. 그 사이 실패하면 SDK 레코드가 남을 수 있지만
ACTIVE/current 포인터가 없으므로 검색에서 노출하지 않습니다. 작업의 재시도/복구가 필요합니다.
프로세스가 RUNNING 중 종료된 작업은 기존 ingestion 복구 절차를 사용합니다.

검색은 SDK `HYBRID` 호출이 아닙니다. 외부 한국어 임베딩을 유지하기 위해 앱이 SDK 테이블 위에서
코사인 벡터 검색과 LIKE 부분문자열 후보를 합칩니다. Oracle Text/BM25를 새로 도입한 것은 아닙니다.
SDK 26.8의 FLOAT64 저장 벡터는 정확 검색 시 FLOAT32로 맞춰 기존 질의 벡터와 비교합니다.
현재는 정확 검색이며 ANN 인덱스 성능을 보장하지 않습니다. 현재 대상의 SDK 색인이 빠지면
부분 결과를 정상 검색처럼 반환하지 않고 V3_SEARCH_INCOMPLETE로 알립니다.

## 설치와 전환

기존 설치를 자동으로 전환하지 않도록 기본 설정은 legacy로 유지합니다.

```sh
./scripts/setup.sh --with-agent-memory
./.venv/bin/alembic upgrade head
./.venv/bin/python -m scripts.source_transfer init
```

- 최신 migration은 vk0016입니다. 원문 ID 매핑을 채우며 기존 원문을 삭제하지 않습니다.
- KNOWLEDGE_V3_STORE_ID(기본 AKKNOWLEDGEV3)는 기존 에이전트 경험 store와 달라야 합니다.
- 기존 데이터가 있으면 [이관 CLI](v3-source-transfer.md)로 준비된 모든 필요한 버전을 enqueue → process → activate합니다.
- SDK 원문/청크와 기존 원문을 검증한 뒤 `.env`에 `KNOWLEDGE_SOURCE_BACKEND=v3`를 설정합니다.
- **API와 임베딩 워커를 모두 재시작**합니다. 한쪽만 바꾸면 새 READY 자료의 SDK 색인이 누락될 수 있습니다.
- 빈 신규 설치에서는 기존 자료 이관 없이 store 초기화 후 v3로 시작할 수 있습니다.
- v3 이후 새 저장·수정 버전은 워커가 자동 처리하므로 매번 이관 CLI를 실행하지 않습니다.
- SDK store 초기화와 RDF/Property Graph 초기화는 각기 별도입니다.

`setup.sh`는 기존 .env 또는 환경 변수의 v3/Agent Memory 활성화를 읽어 SDK 의존성을 유지합니다.
직접 uv sync를 쓰면 `--extra knowledge --extra mcp --extra agent-memory`를 함께 지정하세요.
모델 가중치·Wallet·암호는 저장소에 포함되지 않습니다. 임베딩 실행 위치와 Kev 선택은 기존 설정 그대로입니다.

## 복구

원문 사본과 기존 벡터가 보존돼 있으므로 문제가 생기면 API/워커를 함께 중지하고
`KNOWLEDGE_SOURCE_BACKEND=legacy`로 되돌린 뒤 함께 시작할 수 있습니다. DB 스키마를 downgrade하거나
SDK 기록을 삭제할 필요가 없습니다. 개별 원문 activate/rollback 이벤트도 보존합니다.
개별 ACTIVE를 rollback하면 그 원문이 있는 범위의 v3 검색은 불완전 색인을 경고할 수 있으므로,
전체 서비스 복구에는 설정 전환을 함께 사용하세요.

SDK 장애 시 새 저장은 READY가 되지 않고, 기존 SDK 원문 읽기는 오류를 반환합니다. 읽기 장애를
옛 본문으로 조용히 숨기지 않습니다. 원본·복구 사본 정리는 이 전환의 범위에 포함하지 않습니다.

## 검증 범위

- 기존 기능 계약을 v3에서도 실행: 원문/수정/이력, 실패와 재시도, 오래 걸린 이전 작업의 완료,
  폐기/복원, 사용자·범위·분류 필터, 정확 키워드, 리랭커, PPTX·출처·첨부, 그래프/인덱스 관련 계약.
- 격리 Oracle에서 실제 한국어 임베딩으로 신규 저장→SDK 검색→수정 실패→재시도→과거 원문/그래프 이력→폐기/복원.
- [Oracle 실행 결과](../reference/v3-primary-validation.json).

소규모 기능 검증이며 대용량 검색 품질·지연·다중 프로세스 강제 종료 시험은 별도입니다.
이관 표의 ACTIVE만으로 전체 앱 전환이나 모든 데이터의 품질을 보증하지 않습니다.

### 운영 전환 확인 (2026-11-03)

기존 원문 462개 버전의 일치 확인과 이관 후 실제 MCP 신규 저장·수정·과거 원문 조회까지
완료했습니다. 지식 ID는 유지되고 새 버전마다 SDK 레코드 ID가 달라짐을 확인했습니다.
[운영 검증 결과](../reference/v3-production-validation.md)를 참고하세요.

사용자는 SDK ID를 직접 만들 필요가 없습니다. 저장 응답의 `knowledge_id`를 보관하고,
수정 전 `knowledge_history`에서 최신 `revision_id`를 확인해 `expected_revision_id`로 전달합니다.
`knowledge_get_content`의 `source_storage.store_id`와 `source_storage.record_id`는
해당 버전이 실제 저장된 Agent Memory 위치를 보여줍니다. 제목 변경으로 ID가 바뀌지는 않습니다.


### 새 스키마에서 재현

아래 명령은 ADMIN이 아닌, 운영 데이터가 없는 별도 테스트 계정에 사용합니다.
`--require-empty`는 기존 테이블이 있으면 중단합니다. 자격 증명 파일은 Git에 넣지 않습니다.

```sh
./scripts/setup.sh --with-agent-memory
./.venv/bin/python -m scripts.validate_oracle_installation \
  --env-file /private/path/test.env --expected-schema YOUR_TEST_SCHEMA \
  --apply --require-empty --v3 --graphs --models
```

기존 ADB 서비스에 빈 스키마를 만들어 2026-11-03 실제 실행을 완료했습니다. 신규 계정 생성은
DB 관리자 작업이며 이 검증 도구는 관리자 계정에 앱 객체를 설치하지 않습니다.
