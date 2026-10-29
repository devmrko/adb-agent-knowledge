# adb-agent-knowledge

Agent Knowledge for Oracle ADB

**Codex·Claude 등 AI 에이전트를 위한 지식 저장소 — Kev 판단, 벡터·그래프 검색, 근거와 변경 이력.**

Oracle Autonomous AI Database에 원문과 벡터를 보관하고, 한국어로 검색합니다.
브라우저에서 직접 찾아보거나 Codex·Claude에 연결해 이전 결정과 해결 방법을 활용할 수 있습니다.
Kev가 조회·저장과 검색 경로를 판단합니다. 모델은 로컬 또는 원격으로 연결하며 Docker는 필수가 아닙니다.

**필수 저장소: Oracle Autonomous Database.** 현재 Oracle 벡터·RDF·SQL Property Graph에 맞춘 구현이며 다른 DB로 교체하는 어댑터는 제공하지 않습니다. SQLite는 테스트용입니다.

**릴리스 상태: preview.** 새 Oracle ADB의 전체 설치 검증은 아직 완료하지 않았습니다.

**새 사용자:** [설치 구성과 모델 선택](docs/guides/portable-setup.md)부터 확인하세요.

[시작하기](docs/guides/quickstart.md) · [검색 화면](docs/guides/search-ui.md) · [Codex / Claude 연결](docs/guides/agent-installation.md) · [다른 머신에 적용](docs/guides/multi-machine-memory.md) · [전체 문서](docs/README.md)

## 할 수 있는 일

| 기능 | 동작 |
|---|---|
| 지식 저장 | 텍스트·URL·PDF·PPTX 원문을 저장하고 비동기로 임베딩 |
| 한국어 검색 | 벡터와 키워드 검색을 결합해 관련 지식과 원문 반환 |
| 출처 관리 | 머신 ID와 파일·Git·객체 위치를 버전별로 기록 |
| 요약·인덱스·근거 | Kev로 검색 경로 선택, 여러 인덱스와 원본 위치 연결 ([사용법](docs/guides/index-navigation.md)) |
| 변경 이력·이벤트 | 트리거로 변경 전후 기록, 후속 처리와 근거 재검토 ([사용법](docs/guides/change-history.md)) |
| 공통 RDF 관계 | 여러 노트·프로젝트의 관계를 연결하고 업무/기록 시점별 조회 ([설치](docs/guides/shared-graph.md)) |
| 기억 갱신 | 기존 지식을 보충·수정하고 이전 버전 보존 |
| 사용자별 관리 | 사용자 소유권과 프로젝트 범위로 구분 |
| 에이전트 연결 | MCP + 공통 스킬로 검색·저장·수정; Kev 기본 판단 계층 |

## 시작하기

기존 **Autonomous Database와 Wallet**이 필요합니다. macOS / Linux 기준입니다.

```sh
git clone https://github.com/devmrko/adb-agent-knowledge.git
cd adb-agent-knowledge
./scripts/setup.sh
```

생성된 `.env`의 DB 사용자·비밀번호, Wallet 경로·암호, 접속 별칭을 채웁니다.
[설정 예시와 준비 사항 →](docs/guides/quickstart.md)

```sh
./scripts/run_knowledge.sh --migrate  # 최초 실행: 스키마 준비 + API + worker
# 이후 실행: ./scripts/run_knowledge.sh
```

**검색 화면:** http://127.0.0.1:8000/knowledge

**API 문서:** http://127.0.0.1:8000/docs

로컬 개발 화면은 자동 연결됩니다. 원격/운영 환경이나 자동 연결을 끈 경우 API 토큰으로 연결합니다. 토큰과 Wallet은 Git에 올리지 않습니다.
기본 실행은 이 머신에서만 접속 가능한 개인 개발 환경입니다.

## Codex / Claude에서 사용하기

공개 저장소 이름과 연결 식별자는 다음처럼 구분합니다. 기존 사용자 연결을 유지하기 위해
MCP·스킬 이름은 변경하지 않았습니다. 이름이 다르다고 다른 프로젝트를 설치하는 것은 아닙니다.

| 구분 | 이름 |
|---|---|
| Git 저장소 · 체크아웃 폴더 · Python 프로젝트 | `adb-agent-knowledge` |
| 제품 설명 | Agent Knowledge for Oracle ADB |
| MCP 서버 등록명 | `vector_knowledge` |
| 스킬 이름 · 폴더 | `vector-knowledge` |
| Python 애플리케이션 모듈 | `knowledge_app` |


서비스를 실행한 상태에서 원하는 클라이언트를 연결합니다.

```sh
./.venv/bin/python scripts/install_agent.py codex --register-mcp
# 또는
./.venv/bin/python scripts/install_agent.py claude --register-mcp
```

새 세션에서 연결을 확인하세요. 자동 저장은 별도 사용자 동의를 전제로 하며,
동일 지식의 보충·정정은 에이전트가 원문과 이력을 확인해 기존 항목을 수정합니다.
[설치·업데이트·자동 저장 안내 →](docs/guides/agent-installation.md)

## 저장소 구조

```text
knowledge_app/                 API · MCP · 검색 · 웹 화면
migrations/                    지식 저장소 DB 마이그레이션
skills/vector-knowledge/       Codex / Claude 공통 스킬
scripts/                       설치 · 실행 · 평가 도구
tests/                         지식 서비스 테스트
docs/                          사용 안내 · 설계 · 검증 결과
packages/python-foundation/    공통 기반 라이브러리와 자체 예제/테스트
alembic.ini                    지식 저장소 마이그레이션 설정
pyproject.toml / uv.lock       서비스 의존성 + 로컬 workspace
```

일반 사용자는 `packages/`를 따로 설정할 필요가 없습니다.
[개발 구조와 검증 명령 →](docs/guides/repository-layout.md)

## 현재 범위

- 기존 지식 보충은 이력을 보존하는 수정입니다. 서버가 유사 문서를 자동 병합하지는 않습니다.
- 한국어 리랭커는 선택 기능이며 실험 결과를 반영해 **기본 비활성**입니다.
- 자동 생성 요약, OCR, Oracle Text/BM25는 아직 지원하지 않습니다.
- 운영 다중 사용자 환경에는 별도 JWT·TLS 구성이 필요합니다.

[검색 평가](docs/guides/search-evaluation.md) · [실측 결과와 한계](docs/reference/knowledge-validation.md)

자동 그래프: [추출 모델 설정·후보 검토·운영 안내](docs/guides/automatic-graph.md)

## 라이선스

프로젝트 코드는 [MIT](LICENSE)입니다. 모델 가중치, 외부 서비스와 의존성은 각자의 라이선스·이용 조건을 따릅니다. [외부 구성 요소](THIRD_PARTY.md)를 참고하세요.
