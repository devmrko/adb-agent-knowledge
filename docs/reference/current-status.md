# 현재 상태와 업데이트 순서 / Current status

기준: 2026-11-03, 사용자 원칙 구현 `063a9cc` 이후 문서 점검. 제품은 v2 preview 0.2.0입니다.
이 문서는 현재 계약을 요약하며, 날짜가 붙은 과거 검증 결과를 덮어쓰지 않습니다.

| 구분 | 현재 동작 |
|---|---|
| 기본 저장소 | Oracle Autonomous AI Database. SQLite는 테스트용 |
| 기본 관계 추출 | agent 모드: Codex·Claude가 추출. 선택적 service 모드만 별도 생성 모델 사용 |
| 임베딩 | 기본 한국어 1024차원 모델을 API/worker 머신에서 실행. 원격 OpenAI 호환 제공자 선택 가능 |
| Kev | 별도 로컬/원격 판단 서비스. 조회·저장·탐색 경로 판단, 사실 확정/벡터 생성 아님 |
| DB 마이그레이션 | 최신 vk0014. RDF·Property Graph·SDK 저장소는 선택 기능별 별도 초기화 |
| MCP 도구 | core17 / memory22 / graph31 / organize28 / operations29 / full64 |
| 매 요청 훅 | 클라이언트별 설치 필요. 원칙 정확 조회 + Kev 판단 + 필요한 기억 조회, 쓰기 없음 |
| 사용자 원칙 | Oracle의 별도 사용자 설정·이력. 웹에서 승인·관리, Kev skip에도 훅이 전달 |
| 웹 지식/메모리 | 조회 전용. 원문·관계 변경은 MCP/API. 원칙 설정만 웹 편집 허용 |
| SDK 메모리 | 선택적 Oracle Agent Memory. 업무 문서·사용자 원칙과 구분 |

## 새 설치·업데이트

1. 서버 소스와 잠긴 의존성을 업데이트합니다. DB/Wallet·API 인증 설정은 개인 환경에 둡니다.
2. 기존 운영 DB는 쓰기 프로세스와 적용 범위를 확인한 뒤 `./.venv/bin/alembic upgrade head`를 실행합니다.
   신규 시작은 `./scripts/run_knowledge.sh --migrate`도 지원합니다. Oracle DDL은 자동 커밋입니다.
3. 같은 버전의 API·worker를 시작하고 MCP 연결을 새 코드로 재연결합니다.
4. 사용하는 기능만 RDF / Property Graph / SDK 초기화와 설정을 적용합니다. 이미 있는 네임스페이스를 무조건 재생성하지 않습니다.
5. 에이전트 클라이언트에서 스킬과 훅을 업데이트합니다. 서버가 먼저 원칙 응답을 지원해야 합니다.
6. 클라이언트별 신뢰/활성화를 확인하고 실제 요청의 check_id와 principle_version을 검사합니다.
7. 웹에서 원칙을 불러와 승인·수정합니다. 새 계정은 빈 목록이며 기본 6개도 초안 추가 후 승인해야 합니다.

`MCP_TOOL_PROFILE`은 서버 시작 설정, `knowledge_tools`는 한 연결의 임시 도구 선택입니다.
훅 설치와는 별개이며, 프로필 전환 후에는 작업 전 프로필로 복귀합니다. 연결 상태만으로
새 코드·도구 목록·훅 실행을 확인했다고 판단하지 않습니다.

## 검증한 범위와 남은 한계

- 최근 기능 검증: ruff/format/mypy와 290개 테스트 통과. 사용자 격리·버전 충돌·CSRF·토큰·마이그레이션 포함.
- 운영 A10 Oracle vk0014 적용, 인증 API 원칙 6개 저장(version1)/이력 및 실제 훅 Kev skip 전달 확인.
- Codex 실제 컨텍스트 주입, Claude 훅 원문 기반 답변은 앞선 검증에서 확인했습니다.
- 웹 편집기 열기·초안 입력은 확인. 확인창에서 브라우저 자동화가 지연돼 전체 웹 저장 클릭 성공은 미검증입니다.
- 원칙 전달은 모델 준수 보장이 아닙니다. 훅 첫 검색의 관련성, 짧은 후속 질문 검색어 개선은 남은 과제입니다.
- 새 ADB 서비스 생성·모든 OS·대규모 성능·모델 준수율을 검증한 것은 아닙니다.
- 원칙 이력은 API 트랜잭션으로 보존합니다. 기존 지식/그래프 감사 트리거와 달리 직접 SQL 변경 감사 트리거는 없습니다.

## English summary

Current schema head is vk0014; product version remains v2 preview 0.2.0. Knowledge, optional SDK memories,
and user-approved principles have distinct purposes. Principles are exact owner configuration, not vector
hits. The client hook always resolves them, including on Kev skip; MCP registration alone does not install
or activate hooks. Update the server/migrations first, restart API and reconnect MCP, then update client
hooks/skills and verify a real prompt. Model compliance is not guaranteed by context delivery.

The web displays knowledge/memories/relations read-only; principles alone have an authenticated editor.
Current tool presets are core17, memory22, graph31, organize28, operations29, full64. Temporary tool changes
are not persisted startup configuration. Latest feature checks passed 290 tests plus static checks;
live Oracle migration, authenticated principle save/history and hook delivery succeeded. Browser editor
loading/drafting was observed, but its full confirmation/save interaction remains unverified due to browser
automation failure. Historical validation records describe their dates, not current unresolved failures.

[설치 / Installation](../guides/runtime-installation.md) · [훅 / Hook](../guides/required-memory-hook.en.md) ·
[원칙 / Principles](../guides/user-principles.en.md) · [한글 전체 안내](../README.md) · [English guides](../en/README.md)

## 이번 문서 점검

README·설치·화면·훅·흐름·모델 위치·이력·한영 문서 색인을 코드와 대조했습니다. SQL 참조는 vk0014의 ORM/SDK lock 27개 테이블 기준으로 재생성했습니다(실제 업그레이드된 컬럼 형식은 migration 이력 기준). Markdown 90개와 상대 링크 319개를 검사했습니다. 과거 스냅샷은 보존하고 현재 안내와 분리했습니다. Oracle 설치 검증 도구의 vk0011 고정값은 Alembic 최신 head 조회로 수정했습니다. 이번 문서 점검에서 별도의 Oracle 초기화나 부하 시험을 재실행하지 않았습니다.
