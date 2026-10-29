> 원본 Foundation README 보관본입니다. 지식 서비스 설치는 [루트 README](../../../README.md)를 사용하세요.

# Python Foundation

FastAPI 기반의 재사용 라이브러리와 실행 가능한 Project 예제입니다.
Spring Foundation과 개발 방법론·CRUD HTTP 계약을 공유하되 Python 방식으로 구현합니다.

Python 3.12+ · uv · FastAPI · SQLAlchemy · Pydantic · Alembic.

## 시작

Python 3.12 이상이 필요합니다. uv가 설치되어 있지 않으면 포함된 ./uvw를 사용합니다. 최초 실행 시 프로젝트 내부 .tools에 uv 0.13.1을 설치하며 전역 Python 환경을 바꾸지 않습니다. 인터넷 연결이 필요합니다. 아래 명령의 ./uvw는 이미 설치한 uv로 바꿔 실행해도 됩니다.

```sh
./uvw sync --locked
export FOUNDATION_DEVELOPMENT_PASSWORD='set-a-long-local-password'
./uvw run alembic upgrade head
./uvw run uvicorn example_app.app:create_app --factory --host 127.0.0.1 --port 8000
```

http://127.0.0.1:8000/login 에서 사용자 user로 로그인합니다. 비밀번호는 위 환경 변수입니다.
이 값은 개발 전용이며 저장소에 실제 비밀번호를 커밋하지 않습니다.
SQLite 파일 foundation.db가 생성됩니다. HTML은 Jinja2, CSS는 Bootstrap CDN을 사용합니다.

API /api/v1/projects, 화면 /projects, 공개 health /actuator/health, 인증 필요 OpenAPI /openapi.json.
개발용 공유 작업 공간이며 소유권·테넌트 격리를 구현한 제품은 아닙니다.
운영 세션은 외부 SessionStore와 사용자 인증 구현이 필요합니다.

## 검증

```sh
uv run ruff check .
uv run mypy
uv run pytest
uv build
```

[아키텍트 설계 판단 가이드](architecture-guide.md) · [설계](design/foundation.md) · [사용법](how-to.md) · [검증 결과](validation.md)

배포 패키지 이름은 devmrko-python-foundation, import는 python_foundation입니다.
예제 앱과 DB 마이그레이션은 소비 앱의 소유이며 라이브러리 wheel에 포함하지 않습니다.
실제 Oracle, 운영 인증 공급자·세션 저장소, PyPI 배포는 별도 검증/구성 범위입니다.
