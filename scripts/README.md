# 명령 용도별 안내

모든 명령은 저장소 루트에서 실행한다. 이 폴더에는 사용자 진입점과 개발·운영 도구가 함께
있으며, 기존 명령·Python import 경로를 보존한다. 일반 사용자가 모든 스크립트를 실행할 필요는 없다.

| 용도 | 진입점 | 실행 효과 |
|---|---|---|
| 최초 설치 | `./scripts/setup.sh` | 잠긴 의존성 설치, 없을 때만 개인 `.env` 생성 |
| 서비스 실행 | `./scripts/run_knowledge.sh --migrate --kev` | 선택적으로 테이블 migration·Kev 실행, API/워커 관리 |
| 에이전트 연결 | `python scripts/install_agent.py codex --register-mcp` | 선택한 이름으로 MCP 등록, 공통 스킬 설치 |
| 설정 확인 | `python -m scripts.doctor` | 읽기 전용 점검. `--db`는 실제 접속·스키마 확인 |
| Kev 준비 | `./scripts/setup_kev.sh` | 별도 Kev checkout·Python 환경 설치 |
| RDF 준비 | `python -m scripts.prepare_knowledge_rdf` | Oracle RDF 초기화. 관리자 권한 자동 부여 없음 |
| Property Graph | `python -m scripts.setup_property_graph` | 기본은 조회, `--apply`는 View·Graph 생성/재정의 |
| 로컬 관계 모델 | `python -m scripts.configure_local_graph` | 기본은 미리보기, `--apply`는 해당 `.env` 항목 변경 |

위 표의 `python`은 설치된 `./.venv/bin/python`을 사용한다.

## 운영 도구

- `run_knowledge_api.sh`, `run_knowledge_worker.sh`, `run_kev.sh`: 프로세스를 따로 관리할 때 사용.
- `run_configured_knowledge_mcp.sh`: 설치 도구가 등록하는 MCP 진입점. 로컬/SSH 선택.
- `run_knowledge_mcp.sh`, `run_remote_knowledge_mcp.sh`: 각 연결 방식의 실행 도구.
- `recover_knowledge_jobs.py`, `batch_graph_by_date.py`: 실패 작업 복구·관계 재처리. 대상과 옵션을 확인한 후 실행.
- `backfill_navigation.py`, `migrate_workflow_graph.py`: 기존 데이터 보완·이전. 새 설치 필수 단계가 아님.
- `setup_workflow_rdf.py`, `setup_shared_rdf.py`, `setup_navigation_rdf.py`: RDF 세부 초기화 도구.
  새 설치는 상위 진입점 `prepare_knowledge_rdf`를 사용.
- `configure_agent_memory.py`: 사용자가 선택한 로컬 메모리 정책 적용·복원. 기본 설치에서 자동 실행하지 않음.

## 검증·평가 도구

`smoke_*.py`는 실제 API/DB에 검증용 지식을 기록할 수 있다. `check_knowledge_db.py`와
`check_local_graph.py`는 각각 DB 접속·로컬 모델 검증이며, 모델 검사는 추론 서버가 필요하다.
`evaluate_knowledge.py`, `tune_reranker.py`는 자체 평가 데이터와 설정으로 검색 품질을 측정한다.
자세한 효과와 입력은 각 파일 설명 및 `--help` 지원 여부를 확인한다.

[설치](../docs/guides/portable-setup.md) · [개발·운영](../docs/guides/knowledge-development.md)

## Oracle 그래프 실습

`./uvw run python -m scripts.demo_graph_relations --apply`는 project:graph-demo에 가상 Cafesto
원문·개체·관계를 등록하고 별칭과 근거/의존 경로를 조회합니다. --apply 없이 실행하면 쓰지 않습니다.
[초기화·SQL·조회 예제](../docs/guides/oracle-graph-examples.md)를 먼저 확인하세요.
