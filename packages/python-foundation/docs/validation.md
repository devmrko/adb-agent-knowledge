# 검증 결과

검증일: 2026-10-15. macOS arm64 / Python 3.14.6 및 3.12.15 / uv 0.13.1.
정확한 의존성은 uv.lock에 고정합니다. 첫 검증 환경은 FastAPI 0.143.1, Starlette 1.8.0, Pydantic 2.14.1, SQLAlchemy 2.0.54, Alembic 1.20.0, PyJWT 2.15.1입니다.

| 검사 | 결과 |
| --- | --- |
| Ruff lint / format | 통과 |
| mypy strict | 라이브러리와 예제 통과 |
| pytest | Python 3.14와 3.12에서 각각 33개 통과 |
| DB | Alembic SQLite migration, commit, 복수 변경 rollback, commit 실패 후 연결 반환, read-only ORM flush 거부, 실제 낙관적 잠금 충돌 |
| 인증 | 세션 회전·폐기·TTL, CSRF, 권한, token/mixed 세션·Basic 우회 차단, root_path 경계, JWT 서명·issuer·audience·exp·nbf·type |
| 오류/화면 | ProblemDetail, 입력 비노출, 안전한 500, requestId, Jinja escaping, OpenAPI |
| 실제 Python 서버 | 임시 SQLite DB, Uvicorn 프로세스, 로그인·CSRF, CRUD HTTP 계약 통과 |
| 실제 Java 서버 | Spring Foundation bd3f97d 계열 실행 JAR을 별도 임시 DB로 기동, Python과 같은 CRUD 계약 통과 |
| 배포 | wheel/sdist 빌드 성공 |
| 독립 소비 | 별도 venv에 wheel만 설치, 소스 import 없이 6개 생성 앱의 기동·인증·health 검증 |
| 생성기 | SQLite/Oracle × session/token/mixed, 기존 디렉터리 덮어쓰기 거부 |

실제 Oracle 연결은 미검증입니다. 생성 앱 6종의 실행 검증은 DB URL을 SQLite로 대체한 배포·구성 검사이며 Oracle 호환성의 증거가 아닙니다. 영속 작업 adapter 구현, 운영 SessionStore, 실제 JWKS 네트워크·키 회전, OIDC/opaque, 외부 관측 exporter, 부하·다중 서버·장시간 장애 시험도 후속 범위입니다.

Starlette의 TestClient가 HTTPX 호환 adapter에 대해 deprecation 경고를 출력합니다. 현재 고정 조합의 테스트는 통과하며, 테스트 transport 변경은 별도 의존성 업그레이드 검증 대상으로 기록합니다. 경고를 숨기지 않습니다.

CI는 Python 3.12와 3.14에 같은 lint/type/test/build/wheel/프로세스 검증을 구성합니다. CI의 실제 결과는 해당 커밋의 GitHub Actions 실행에서 확인합니다. 로컬에서는 Python 3.12와 3.14를 검증했으며 기타 버전까지 검증했다고 주장하지 않습니다.

## 재현

```sh
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
uv run python scripts/smoke_runtime.py
uv build
uv run python scripts/verify_wheel.py
```

Java와 같은 계약을 재검증하려면 scripts/smoke_runtime.py에 --java-jar와 --java를 지정합니다. 이 스크립트는 자체 프로세스·임시 DB만 만들고 종료합니다. 이미 실행 중인 앱을 검증하는 scripts/check_contract.py는 Project 데이터를 생성·삭제하므로 전용 개발 환경에서만 실행합니다. 자격 증명은 CONTRACT_PASSWORD/CONTRACT_ACCESS_TOKEN 환경 변수로 전달합니다.
