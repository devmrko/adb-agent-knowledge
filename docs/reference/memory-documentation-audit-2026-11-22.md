# 기억 문서와 현재 코드 대조 · 2026-11-22

기준 소스는 `hotfix/rdf-index-web-ui`의 `273eb7f`(기억 보존 설명 포함)와 이 문서 점검 변경입니다. 이 점검은 README·기억 유형·Agent Memory 연결·v3 저장·관련 훅/웹/원칙 가이드의 현재 설명을 대상으로 했습니다. 모든 과거 설계·검증 문서를 새 계약으로 고쳐 쓴 전체 저장소 감사는 아닙니다.

## 버전과 활성 설정

| 항목 | 소스·새 설치 기준 | 점검한 원격 설정·응답 | 해석 |
|---|---|---|---|
| 공개 릴리스 기준 | `v0.3.0-alpha.1`, 패키지 `0.3.0a1`, 소스 API `0.3.0-alpha.1` | OpenAPI `info.version=0.3.0` | 원격에 다른 버전 메타데이터가 남아 있습니다. 정식 릴리스/기능 동등성의 증거가 아닙니다. 이번에는 문서에서 차이를 공개했고 실행 버전을 임의 변경하지 않았습니다. |
| 수정 문서·UI·RDF | `hotfix/rdf-index-web-ui` | 해당 UI·RDF는 앞선 hotfix에서 반영 | 기존 알파 태그와 main에는 이 브랜치가 아직 병합되지 않았습니다. 태그 복제와 hotfix 사용을 구분합니다. |
| Agent Memory SDK | `pyproject.toml`·`uv.lock`의 `26.8.0` 고정 | 설치 패키지 `26.8.0` | 최신 upstream 전체를 뜻하지 않고 이 프로젝트가 사용하는 버전입니다. 로컬 개발 가상환경에는 선택적 SDK가 설치되지 않았으며 그 사실도 실제 Oracle 실행과 구분합니다. |
| 업무 지식 저장 경로 | `KNOWLEDGE_SOURCE_BACKEND=legacy` 기본 | `v3` | SDK 기반 업무 원문·검색 설명은 명시적으로 v3를 켠 경로입니다. |
| SDK 에이전트 경험 기억 | `AGENT_MEMORY_ENABLED=false` 기본 | `true` | 지원 기능과 신규 설치의 기본 활성화를 혼동하면 안 됩니다. |
| 기억 저장소 기본 식별자 | `AKKNOWLEDGEV3` / `AKMEMORY` | 같은 값 | 두 저장소는 단기/장기가 아니라 업무 지식/경험 기억의 구분입니다. |
| 업무 관계 추출 | 기본 `agent` | 원격 설정 `agent` | SDK의 `extract_memories=False`와 별개 설정입니다. |
| MCP 도구 프로필 | CLI 미지정 시 `core` | 원격 `.env`는 `memory` | 일시적 도구 전환과 시작 기본값을 구분합니다. |

원격 설정은 비밀값을 제외한 허용 목록만 읽었습니다. 임의의 모든 프로세스 환경·운영 데이터·모든 배포 머신을 조사한 결과는 아닙니다.

## 구현 대조표

| 문서 주장 | 확인한 구현 | 결과 |
|---|---|---|
| SDK 장기 기억의 자동 대화 추출을 사용하지 않음 | `SDKRepository.connect`: `MemoryExtractionConfig(extract_memories=False)` | 일치 |
| SDK 단기 메시지·컨텍스트 카드 통합 없음 | 앱 호출 AST에서 `add_message`/`add_messages`/`get_context_card` 호출 없음. `create_thread`는 `enable_context_summary=False` | 일치. 단기 기능 성능을 비교해 배제한 기록이라는 뜻은 아님 |
| 장기 기억의 출처와 thread 수명 분리 | `AgentMemoryService.save`가 `origin_thread_id`를 metadata에 기록하고 SDK `thread_id`를 넘기지 않음 | 일치 |
| SDK memory 자동 연결 비활성 | `add_memory(..., autonomous_linking=False)` | 일치. 업무 RDF의 별도 추출과 구분 |
| 공개 기억 종류 | `MemorySave.memory_type`: memory/fact/preference/guideline; `MemoryKind`: DOCUMENT/DECISION/PREFERENCE/FACT/PROCEDURE/EPISODE | 일치. 의미/일화/절차의 개념과 API enum은 별개 |
| 두 저장소와 기존 업무 계약 병존 | `VersionedMemoryPilot`, `KnowledgeService`, v3 검색 repository, 기본 Settings | 일치. legacy 기본과 v3 활성 경로를 명확히 표시하도록 문서 수정 |
| 훅은 제한된 최근 문맥을 사용 | `hook_context.py`: 같은 세션의 최대 2개 발췌·총 1200자, 도구 출력/추론 제외 | 한글 설명과 새 기억 가이드는 일치. 영문 훅의 ‘transcripts not read’를 수정 |
| 웹은 지식 조회 전용·원칙만 승인 편집 | `READ_ONLY=true`, 원칙 PUT 예외, 원칙 네이티브 dialog | 동작 설명은 일치. 개편 전 위치·펼치기 안내를 수정 |
| 프로필별 도구 수 | 실제 `create_server(..., profile=...)`의 `list_tools()` | core17 / memory22 / graph31 / organize28 / operations29 / full64, 문서와 일치 |
| 현재 DB migration | `.venv/bin/alembic heads` | `vk0016` 한 head, 문서와 일치. 이번에 운영 DB migration을 실행한 것은 아님 |
| 긴 세션의 내용 보존 | 선택적 저장 정책·버전 보존·MCP 조회·원문 읽기 경로 | 구현 취지와 일치. 저장/검색/올바른 적용을 구분하고 무손실 기억 보장은 하지 않음 |

SDK 관련 다섯 파일(`agent_memory_contracts.py`, `agent_memory_service.py`, `agent_memory_repository.py`, `navigation.py`, `v3_pilot.py`)의 SHA-256이 로컬과 원격에서 일치함을 확인했습니다. 이 다섯 파일의 비교를 전체 배포의 동일 커밋 증명으로 확대하지 않습니다.

## 정정한 문서

- 한영 README·기억 유형 가이드: 공개 태그/후속 hotfix/원격 버전 문자열, 선택적 활성화와 설치 기본값을 구분했습니다.
- 영문 필수 훅 가이드: 최근 transcript의 제한된 발췌를 읽는 현재 동작을 반영했습니다. 한글의 고정 ‘22개 도구’ 설치 문구는 프로필을 바꾸지 않는다는 실제 계약으로 바꿨습니다.
- 검색 화면·한영 사용자 원칙 가이드: 작업공간 탐색 버튼, 모바일 아이콘, 원칙 dialog의 닫기·포커스 복귀를 반영했습니다.
- Agent Memory 가이드: 275개 테스트는 2026-11-02 당시 결과라고 표시하고, 이미 구현된 v3를 단순 제안으로 부르던 링크 문구를 고쳤습니다.
- 한영 v3 가이드: SDK 주 저장·검색의 적용 조건이 `KNOWLEDGE_SOURCE_BACKEND=v3`임을 첫 설명에 표시했습니다.
- 현재 상태 문서: 이번 점검을 앞에 추가하고 2026-11-04 이후 과거 검증 기록은 날짜와 함께 보존했습니다.

## 확인 범위와 한계

기본값·타입·SDK 설정·출처 연결·단기 API 호출 부재·훅 분량·UI 설정·잠긴 의존성·6개 도구 카탈로그는 읽기 전용 코드 대조와 검증 스크립트로 확인했습니다. 변경 문서 15개의 링크 222개·코드 블록·포맷을 확인했습니다. Ruff 검사·형식 검사·mypy 통과, 전체 pytest 347개 통과(기존 Starlette/httpx deprecation warning 1개)입니다.

새로운 DB 쓰기·SDK 초기화·마이그레이션·실제 기억 저장/삭제·장애 주입·무손실 기억/검색 품질 시험은 수행하지 않았습니다. 과거 측정 수치와 검증 기록은 당시 환경의 결과로 유지합니다. 원격 API의 버전 문자열 차이는 문서 정정으로 없어지지 않으며, 후속 릴리스·배포 관리에서 별도로 정리할 사항입니다.

## English summary

The new memory-type rationale matches the checked implementation. Fresh defaults remain legacy storage and disabled optional SDK agent memory; the checked remote configuration enables v3 and SDK memory, with SDK 26.8.0. Five relevant source files match remotely by hash. SDK extraction, automatic memory linking and thread summaries are disabled; no app message/context-card call path exists. These facts do not establish lossless capture or perfect retrieval.

Corrected stale English hook transcript wording, pre-redesign web/principles instructions, unlabeled historical test counts and v3/version/default ambiguities. Release tag, unmerged hotfix branch and remote OpenAPI version 0.3.0 are now explicitly distinguished. The latter differs from source API metadata 0.3.0-alpha.1; no runtime version was changed by this documentation audit. This is a bounded code/configuration review, not a full historical-doc audit or new live Oracle lifecycle test.

Validation: code/configuration assertions, 222 links across 15 changed documents, Ruff, format and mypy passed; pytest passed 347 tests with one existing deprecation warning.
