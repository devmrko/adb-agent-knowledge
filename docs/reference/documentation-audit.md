# Documentation audit and migration validation — 2026-10-30

점검 기준: 공개 저장소 adb-agent-knowledge, 기존 HEAD 32262dc 및 이 변경의 vk0011.
전체 문서의 구조 검사와 주요 사용 계약의 코드 대조를 구분한다. 모든 설치 명령을 실제 서버에서
실행했다는 의미가 아니며, 과거 검증을 이번에 다시 수행한 것처럼 표시하지 않는다.

## 범위와 발견 사항

- 기존 추적 Markdown 80개(루트, guides, English, design, reference, skill/config, Foundation)의
  상대 링크 200개와 JSON 예제 15개를 먼저 검사했다. 이후 추가 문서까지 다시 구조 검사를 수행한다.
- 현재 사용 가이드의 모델 역할·실행 위치·설치/업데이트·인증·인덱스·관계·이력 계약을 관련 소스와 대조했다.
- 설계 30개와 과거 검증/비교/라이선스 기록은 역사적 자료로 표시했다. 과거 실측 숫자와 미구현
  목록을 현재 상태로 바꾸지 않았다. 외부 프로젝트·가격·라이선스 전체를 재조사한 감사는 아니다.
- Foundation은 독립 라이브러리 문서임을 명시하고, 지식 DB migration과 예제 migration을 구분했다.
  이전 원본 README는 보관본으로 유지한다. English 상세 문서 전체 번역을 완료했다는 뜻은 아니다.

| 수정한 내용 | 대조한 구현 |
|---|---|
| v2 관계 추출은 에이전트, Kev는 판단, 임베딩은 API/worker 또는 원격 모델 | mcp_server.py, launcher.py, embedding.py, graph_auto_service.py |
| 웹 인증: Bearer 메모리 보관과 HTTPS 쿠키 세션 구분 | browser_session.py, static/app.js |
| 그래프 날짜 입력: 브라우저 로컬 시간 → UTC | static/app.js |
| 반복 RDF 초기화: prepare_knowledge_rdf 진입점 사용 | scripts/prepare_knowledge_rdf.py |
| 업데이트 시 최신 migration·동일 버전 워커·MCP 재연결 | launcher.py, migrations/versions/ |
| 추출 operations-v3, 세 정책, PARTIAL 상태 | graph_auto_contracts.py, graph_auto_service.py |
| agent 관계 처리와 service auto_verified 그림 구분 | graph_auto_service.py, graph_ops_service.py |
| 최신 테이블 23개를 포함하는 SQL 참조 | models.py, audit_models.py, graph_auto_models.py, graph_ops_models.py |
| 이력·트리거 자동 초기화 및 적용 범위 | audit_schema_v8.py, audit_schema_v11.py, vk0008/vk0011 |

과거 모델 가격 문구는 현재 설치 가이드에서 제거했다. 서비스 모델 ID는 사용자가 선택하는 예제로
표시한다. DB health가 실제 SELECT를 수행한다는 설명과 검색 최대 20개 표시는 코드와 일치해 유지했다.

## 사용자 요청으로 추가한 vk0011

전체 migration은 원문·관계 버전 및 감사 이력 테이블과 트리거를 함께 초기화한다.
vk0011은 기존 다섯 그래프 테이블의 변경을 감사하고 vk_g_operation의 수정·삭제를 막는다.
이미 적용된 migration을 수정하거나 과거 행의 이력을 소급 생성하지 않는다.

```sh
# 같은 DB를 쓰는 writer들을 중지하고 최신 코드를 준비한 뒤
./scripts/run_knowledge.sh --migrate
# migration만 적용할 경우:
./uvw run alembic upgrade head
```

CREATE TRIGGER 권한이 필요하다. RDF/Property Graph 초기화는 별도다. 감사 SQL 참조 파일은
실행용 installer가 아니며 migration-only 트리거를 포함하지 않는다. 실제 설치는 Alembic을 사용한다.
서비스 모드의 context 없는 쓰기는 DIRECT_SQL로 보일 수 있으므로 이를 사람의 실행으로 단정하지 않는다.

## 이번에 실행한 검사

- Ruff check 통과, format check 213개 파일 통과, mypy 62개 소스 파일 통과.
- 전체 pytest: 254개 통과(14.01초), 추가 감사 migration·격리 테스트 포함.
- 실제 SQLite 빈 DB 초기화, vk0010 → head 업그레이드, 반복 migration/트리거 설치.
- 기존 행 보존·과거 이력 미생성, 다섯 테이블의 변경 스냅샷, outbox 동시 기록.
- 트랜잭션 rollback, 감사 실패 시 원본 변경 취소, owner/id 변경 차단, operation 이력 수정·삭제 거절.
- 개체 식별/검토의 감사 사용자 연결 및 다른 사용자의 이력 접근 차단.
- Oracle 트리거 SQL 생성 및 USER_ERRORS 실패 처리 경로(mock). 실제 Oracle 컴파일은 아님.
- 최종 Markdown 82개, 상대 링크 240개, JSON 예제 15개 검사: 오류 없음.
- SQL 참조의 ORM 테이블 23개 및 컬럼 일치 확인, git diff --check 통과.

## 이번에 실행하지 않은 검사

새 Oracle ADB 생성·Wallet 연결·vk0011 실제 적용, 실제 모델 다운로드/추론, 실브라우저 UI 검증,
성능·부하 실측과 외부 링크 전체의 네트워크 접근 검사는 수행하지 않았다. 운영 서버도 변경하지 않았다.
기존 Oracle/모델 검증은 [날짜별 검증 기록](public-release-validation.md)의 당시 범위로만 해석한다.
Native 지식 MCP는 Transport closed여서 이번 결과의 지식 DB 저장은 완료하지 못했다.

## English summary

This change audits documentation structure and checks key user-facing contracts against source. It fixes
browser authentication, timezone, safe RDF initialization, upgrade requirements, extraction schema/policies,
and the agent/service workflow distinction. Historical design/measurement records remain explicitly dated.
The SQL reference now covers all 23 ORM tables, while Alembic remains the installer for tables and triggers.

Migration vk0011 adds five graph row-audit triggers and append-only operation-history protection. Tests
cover fresh and incremental SQLite migrations, preservation, snapshots, rollback, audit failure atomicity,
actor attribution and owner isolation. Oracle SQL/error handling checks are not live Oracle compilation.
No production deployment or fresh-ADB/model/browser validation is claimed. See the linked current guides
for setup; the remaining detailed historical documents are primarily Korean.

## Subsequent live validation

The later [2026-10-30 Oracle and runtime validation](oracle-installation-validation.md) executes isolated Oracle setup and actual model probes. Earlier unverified statements above describe the earlier check, not the result of this follow-up.
