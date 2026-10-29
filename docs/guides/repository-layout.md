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
| `scripts/` | 사용자 설치/실행, 로컬 평가 도구 |
| `skills/` | 에이전트에 설치할 공통 지식 스킬 |
| `packages/python-foundation/` | 기반 라이브러리 소스, 별도 예제·migration·tests·docs |

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
