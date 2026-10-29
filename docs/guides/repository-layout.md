# 저장소 구조와 개발

루트는 **Agent Knowledge for Oracle ADB 서비스 실행 프로젝트**이다. `pyproject.toml` 이름도 `adb-agent-knowledge`이며,
앱은 체크아웃에서 실행한다. 공통 Foundation은 `packages/python-foundation`의 별도 uv workspace
패키지로 설치한다. 공개 PyPI에서 Foundation을 내려받을 필요는 없다.

| 위치 | 역할 |
|---|---|
| `knowledge_app/` | API, 인증 연결, repository/service, 임베딩, 리랭커, MCP, worker |
| `knowledge_app/static/` | 검색 웹 화면 HTML/CSS/JS |
| `migrations/` + `alembic.ini` | 지식 DB 전용 migration, 기존 vk_alembic_version 유지 |
| `tests/` | 지식 서비스와 MCP·평가·설치 테스트 |
| `scripts/` | 설치·운영·평가 진입점. [용도별 안내](../../scripts/README.md) |
| `skills/adb-agent-knowledge/` | Codex·Claude에 설치할 공통 지식 스킬 |
| `packages/python-foundation/` | 기반 라이브러리 소스, 별도 예제·migration·tests·docs |

## 이름과 폴더를 나눈 기준

- `adb-agent-knowledge`: 공개 저장소·프로젝트·스킬 이름.
- `adb_agent_knowledge`: 기본 MCP 등록 별칭. `--mcp-name`으로 바꿀 수 있다.
- `knowledge_app`: 내부 Python 모듈. 제품명과 달라도 정상이며 기존 실행·import 경로를 유지한다.
- `packages/python-foundation`: 실제 인증·트랜잭션·오류 처리 의존성. 서비스 코드와 별도로
  배포 가능한 wheel·자체 예제·테스트를 격리한다. 앱 사용자가 이 예제를 실행할 필요는 없다.
- `docs/guides`: 사용·운영 안내. `docs/design`은 개발 설계, `docs/reference`는 검증·참조 자료.
- 정책 블록의 `vector-knowledge` 식별자와 기존 백업 경로는 복구 호환용이며 제품 이름이 아니다.

새 사용자는 README → 설치 가이드 → 에이전트 연결 순서로 읽는다. 소스 변경 없이 실행할 때
`knowledge_app`, `migrations`, `tests`, `packages`를 직접 수정하지 않는다.
대규모 src/ 이동이나 scripts import 경로 변경은 이번 공개 정리에 포함하지 않았다.

## 이전 체크아웃에서 업데이트

```sh
./scripts/setup.sh
```

기존 `.env`는 유지하고 이동한 Foundation 패키지의 editable 경로를 갱신한다.
실행 중인 API/worker는 다시 시작한다. MCP 실행 스크립트 경로는 유지하므로 등록 변경은 필요 없다.
마이그레이션 경로가 `knowledge-alembic.ini`에서 `alembic.ini`로 바뀌었다.
DB 테이블명과 revision ID는 동일하며, 이 폴더 정리만으로 운영 DB migration을 실행할 필요는 없다.

## 검사

저장소 루트에서:

```sh
./uvw run --no-sync ruff check .
./uvw run --no-sync ruff format --check .
./uvw run --no-sync mypy
./uvw run --no-sync pytest
```

pytest는 서비스 tests와 Foundation tests를 모두 실행한다.

```sh
./uvw run --no-sync python packages/python-foundation/scripts/smoke_runtime.py
./uvw build --package devmrko-python-foundation
./uvw run --no-sync python packages/python-foundation/scripts/verify_wheel.py --uv .tools/uv/bin/uv
```

wheel은 Foundation 라이브러리용이다. 지식 서비스는 Git 체크아웃 + setup 방식으로 공유한다.
예제 앱과 Foundation 자체 마이그레이션은 `packages/` 아래에만 있으며 서비스 실행에 사용하지 않는다.

## 로컬 전용 파일

`.env`, `secrets/`, `.cache/`, `.run/`, `.venv/`, `.tools/`, `dist/`는 Git에서 제외한다.
개인 평가 질의와 결과는 `.run/search-eval/`에 보관하고 공유용 커밋에 넣지 않는다.
