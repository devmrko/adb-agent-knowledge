# adb-agent-knowledge 매뉴얼

제품명: **Agent Knowledge for Oracle ADB**. 저장소·체크아웃 폴더는 `adb-agent-knowledge`이며,
MCP 등록명 `vector_knowledge`와 스킬명 `vector-knowledge`는 호환성을 위해 유지합니다.

## 처음 사용하는 분

| 하려는 일 | 문서 |
|---|---|
| 구성 선택과 Oracle 필수 조건 | [설치·모델 선택](guides/portable-setup.md) |
| 저장·조회 아키텍처 이해하기 | [저장·조회 흐름](guides/storage-retrieval-flow.md) |
| OpenRouter 없이 전체 기능 준비 | [Oracle·Kev·로컬 Gemma 설치](guides/local-full-setup.md) |
| 설치하고 실행하기 | [빠른 시작](guides/quickstart.md) |
| 브라우저에서 검색하기 | [검색 화면](guides/search-ui.md) |
| 다른 머신의 메모리 정책 적용 | [여러 머신 설정](guides/multi-machine-memory.md) |
| Codex / Claude에 연결하기 | [에이전트 설치](guides/agent-installation.md) |
| 관계·프로젝트·시점별 조회 | [공통 RDF 그래프](guides/shared-graph.md) |
| 요약·인덱스·근거 탐색 | [인덱스 탐색](guides/index-navigation.md) |
| 머신과 출처 위치 기록 | [출처 관리](guides/provenance.md) |
| 모델·GPU·Kev 설정하기 | [로컬 모델](guides/local-models.md) |

## 운영하거나 개선하는 분

| 하려는 일 | 문서 |
|---|---|
| 변경 감사·후속 이벤트·재검토 | [변경 이력](guides/change-history.md) |
| API·인증·작업 복구 확인 | [개발과 운영](guides/knowledge-development.md) |
| 검색 품질 측정 | [검색 평가](guides/search-evaluation.md) |
| 리랭커 비교 실험 | [리랭커](guides/search-reranking.md) |
| 폴더 구조·테스트·패키징 확인 | [저장소 구조](guides/repository-layout.md) |
| 공개 preview 검증과 남은 범위 | [공개 검증 결과](reference/public-release-validation.md) |
| 과거 검색 실측 기록 | [검색 실측](reference/knowledge-validation.md) |
| Codex 연결 문제 해결 | [Codex 연결](guides/codex-knowledge.md) |
| Claude 연결 문제 해결 | [Claude 연결](guides/claude-knowledge.md) |

## 설계 자료

1. [지식 API](design/0001-knowledge-api/design.md)
2. [MCP 연결](design/0002-codex-mcp/design.md)
3. [기억 수정·폐기·복원](design/0003-memory-lifecycle/design.md)
4. [Kev 판단](design/0004-kev-routing/design.md)
5. [설치와 배포 준비](design/0005-portable-setup/design.md)
6. [검색 평가](design/0006-search-evaluation/design.md)
7. [리랭커](design/0007-reranker/design.md)
8. [검색 화면](design/0008-search-ui/design.md)
9. [저장소 구조 정리](design/0009-repository-layout/design.md)
10. [머신과 출처 위치](design/0010-provenance/design.md)
11. [로컬 화면 자동 연결](design/0011-local-ui-connection/design.md)

12. [노트 편집](design/0012-note-editor/design.md)
13. [업무 흐름 RDF 설계](design/0013-workflow-rdf/design.md)

14. [공통 RDF와 시점별 조회 · 목표 설계](design/0014-shared-temporal-graph/design.md)

15. [요약·인덱스·RDF 참조](design/0015-index-navigation/design.md)

[Oracle 스키마](reference/knowledge-schema.sql) · [향후 기억 기능](design/0002-codex-mcp/memory-roadmap.md)

Foundation 자체 자료는 [내부 패키지](../packages/python-foundation/README.md)에 모았습니다.
서비스 설치와 무관한 예제 앱·템플릿 개발 자료는 그쪽에서 확인하세요.

- [자동 그래프 추출·검토](guides/automatic-graph.md)

- [Oracle 통합 그래프 검색](guides/unified-graph-retrieval.md)

- [새 사용자 설치·모델 선택](guides/portable-setup.md)
- [유사 프로젝트와 그래프 검색 비교](reference/project-comparison.md)

- [관계·경로·근거 통합 검색](guides/related-retrieval.md)
