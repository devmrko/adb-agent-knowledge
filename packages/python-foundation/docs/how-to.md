# 사용과 확장

## 공통 개발 규칙

설계와 완료 기준을 먼저 작성하고 Router → Service → Repository 계층으로 구현합니다. HTTP DTO는 Pydantic 모델, 내부 값 객체는 dataclass를 기본으로 사용합니다. dict[str, object]는 동적 데이터 경계에 한정합니다. 계약은 Protocol, 공통 실행 흐름은 ABC를 사용하고 불필요한 상속은 만들지 않습니다.

Service의 with UnitOfWork 블록이 트랜잭션을 소유합니다. Repository는 commit하지 않습니다. 정상 종료하면 커밋, 예외면 롤백, 커밋 실패도 롤백 후 close합니다. 한 업무에서 여러 Repository를 사용할 때 같은 UoW의 Session을 사용합니다. 내부 Service 호출도 기존 UoW를 명시적으로 전달해야 합니다. 독립 UoW를 새로 만들면 별도 트랜잭션입니다. Java의 REQUIRED 전파를 자동 구현한 것이 아닙니다.

조회 UoW는 ORM 변경 flush를 거부하고 rollback으로 종료합니다. DB 수준 read-only 보장이나 raw SQL 쓰기 탐지를 약속하지 않습니다. Session은 thread/task 간 공유하지 않습니다. DTO는 Session이 열려 있을 때 변환하고 응답에서 lazy loading을 하지 않습니다.

Python의 typing.final은 정적 검사 도구를 위한 약속입니다. Java final처럼 런타임 상속/재정의를 차단하지 않습니다. 이 프로젝트는 코드 리뷰, 타입 검사와 계약 테스트를 함께 사용합니다.

## 오류 선언

```python
from python_foundation.errors import BusinessError, ErrorCategory, ErrorSpec

PROJECT_NOT_FOUND = ErrorSpec("PROJECT_NOT_FOUND", ErrorCategory.NOT_FOUND, "Project not found.")
raise BusinessError(PROJECT_NOT_FOUND)
```

분류는 VALIDATION/NOT_FOUND/CONFLICT/UNAVAILABLE이며 REST에서는 400/404/409/503으로 변환합니다. 원인을 보존하려면 raise BusinessError(spec) from cause를 사용합니다. 예외마다 하위 클래스를 만들 필요는 없습니다. 별도 처리 계약이 있을 때만 타입을 나눕니다.

AuthenticationRequired와 AccessDenied는 401/403이며 세션 HTML 요청은 예제에 login_page가 있으면 로그인 화면으로 보냅니다. 예상하지 못한 예외는 안전한 INTERNAL_ERROR 500입니다. 응답에 원인 메시지, 입력 원문, SQL, 토큰을 넣지 않습니다. 로그도 기본적으로 오류 타입과 requestId만 기록합니다. 원문 stacktrace를 외부 관측 도구로 보낼 때에는 비밀 정보 제외와 접근 권한을 앱이 설계해야 합니다.

RuntimeError만 롤백되는 것이 아닙니다. Python의 BusinessError는 Exception을 상속하고 UoW는 예외가 경계를 빠져나가면 롤백합니다. 중간에서 잡고 정상 반환하면 커밋될 수 있으므로 오류를 삼키지 않습니다.

## DB와 마이그레이션

기본은 파일 SQLite와 SQLAlchemy QueuePool입니다. FOUNDATION_DATABASE_URL, FOUNDATION_POOL_SIZE, FOUNDATION_POOL_TIMEOUT, FOUNDATION_SQLITE_BUSY_TIMEOUT_MS로 설정합니다. 메모리 SQLite는 이 풀 구성에서 지원하지 않습니다. 풀 크기를 늘려도 SQLite 동시 쓰기 제한이 없어지지 않습니다.

Oracle은 uv sync --extra oracle로 driver를 설치하고 FOUNDATION_DATABASE_URL을 oracle+oracledb 형식으로 지정합니다. 비밀번호 URL 인코딩 등은 SQLAlchemy URL 규칙을 따릅니다. SQLAlchemy 풀 하나만 사용하며 driver pool을 중첩하지 않습니다.

예제 실행 전에 uv run alembic upgrade head를 명시적으로 실행합니다. 적용한 migration을 수정하지 않고 후속 revision을 추가합니다. 앱 시작 시 create_all로 스키마를 임의 변경하지 않습니다. Oracle dialect와 동일 migration 경로를 제공하지만 실제 Oracle 엔진의 DDL·잠금·타입·성능은 아직 검증하지 않았습니다.

## 인증 설정

| 모드 | 경계 |
| --- | --- |
| session | API와 화면 모두 서버측 세션; 변경 요청은 CSRF |
| token | 보호한 경로는 Bearer 전용; 로그인 화면 없음 |
| mixed | /api 및 /api/**는 Bearer 전용; 그 외 화면은 세션 |

FoundationSettings의 auth_mode 또는 FOUNDATION_AUTH_MODE로 선택합니다. 인증이 필요한 API에는 Depends(current_actor)를 선언합니다. 이 dependency는 세션 변경 요청의 X-CSRF-TOKEN을 확인합니다. HTML form은 security.authenticate dependency와 security.check_csrf(request, form_token)를 함께 사용합니다. 새 경로에 dependency를 생략하면 보호되지 않으므로 라우터·endpoint 리뷰와 테스트에서 확인해야 합니다. install_web은 오류/요청 ID를 설치하며 모든 경로에 인증을 자동 강제하는 기능은 아닙니다.

Actor.require("권한")로 기능 권한을 검사할 수 있습니다. 자원 소유권·테넌트 권한은 Service의 AuthorizationPolicy 구현에 둡니다. 예제는 ROLE_USER 또는 SCOPE_project:write에 변경을 허용하는 공유 작업 공간입니다. 다른 사람의 Project를 분리하는 제품 권한 모델은 아닙니다. Actor는 issuer+subject로 식별하며 이메일을 전역 ID로 사용하지 않습니다.

세션 쿠키에는 무작위 ID만 저장합니다. 개발 MemorySessionStore는 용량과 TTL이 제한된 단일 프로세스 저장소입니다. 로그인 시 ID를 회전하고 로그아웃하면 서버측 상태를 삭제합니다. production에서 session/mixed를 사용하면 공유 SessionStore 구현과 Secure 쿠키가 필수입니다. 예제/생성 앱의 development_password 인증은 운영에서 허용하지 않으며 별도 authenticate_user 구현이 필요합니다. 로그인 시도 제한과 운영 사용자 저장소·SSO는 인증 공급자/게이트웨이 정책과 함께 구성합니다.

JWT는 FOUNDATION_ISSUER, FOUNDATION_AUDIENCE, FOUNDATION_JWKS_URL을 모두 요구합니다. issuer와 JWKS는 신뢰하는 HTTPS 주소여야 합니다. RS256 서명, issuer, audience, subject, exp, nbf(있으면), typ=at+jwt/application/at+jwt를 검증합니다. 시간 오차 허용은 60초입니다. scope를 SCOPE_ authority로 변환하며 토큰의 임의 roles는 자동 신뢰하지 않습니다. 일반 typ=JWT ID token, 잘못된 서명·만료·대상 토큰은 거부합니다.

TokenVerifier를 교체하는 경우 동일한 검증 책임을 구현체가 소유합니다. 토큰 발급 서버, OIDC 로그인 및 opaque introspection adapter는 제공하지 않습니다. 공개 health는 인증 없이 접근되며 DB 장애 시 안전한 오류 응답이 반환됩니다. OpenAPI는 예제에서 인증된 요청에만 제공합니다.

## 비동기와 작업

SQLAlchemy 동기 Service를 호출하는 FastAPI 경로는 def로 둡니다. async def 안에서 동기 DB나 HTTP 호출을 직접 실행하지 않습니다. async 경로에서 동기 Service가 필요하면 업무 단위 전체를 threadpool로 넘기고 그 안에서 UoW를 열고 닫습니다. Session을 만들고 다른 스레드로 넘기지 않습니다.

HTTPX async client는 비동기 외부 호출에 사용합니다. CPU 연산은 별도 프로세스나 worker로 분리합니다. FastAPI BackgroundTasks, asyncio.create_task, threadpool 호출은 프로세스 종료 후 복구되는 영속 작업 엔진이 아닙니다.

DurableJobs는 외부 큐/worker를 연결하는 Protocol입니다. 첫 버전에는 구체적인 큐 엔진이 없습니다. adapter는 영속 저장, actor별 접근, 멱등성, 동시 실행·큐 용량, 재시도·fencing, 작업 보관 기간을 구현해야 합니다. 업무 저장과 작업 등록이 원자적이어야 한다면 같은 트랜잭션의 Outbox를 설계합니다.

## HTTP 클라이언트와 운영

http_client/async_http_client는 명시적인 timeout과 연결 상한을 사용하고 redirect·retry·환경 proxy 자동 사용을 끕니다. 신뢰하는 설정으로 base_url을 정하고 요청 입력 URL을 그대로 사용하지 않습니다. 앱 lifespan에서 생성하고 종료 시 close/aclose하며 호출마다 새 연결 풀을 만들지 않습니다.

remote_call/async_remote_call은 HTTPX 오류를 안전한 REMOTE_SERVICE_FAILED로 바꿉니다. 공급한 함수에서 response.raise_for_status()를 호출해야 HTTP 오류가 분류됩니다. 예상한 외부 404는 업무 adapter에서 해석합니다. timeout이 발생해도 상대 서버에서 쓰기가 완료됐을 수 있으므로 자동 재시도하지 않습니다.

requestId는 서버가 생성하고 X-Request-ID와 오류 본문에 넣습니다. ContextVar가 요청 경계에서 복원됩니다. configure_logging은 python_foundation logger의 JSON 출력을 구성하며 Uvicorn/SQLAlchemy 등 모든 logger 설정을 강제로 덮어쓰지 않습니다. 외부 OpenTelemetry exporter와 수집 서버는 별도 설정 범위입니다. job/user ID를 지표 태그로 무제한 추가하지 않습니다.

## 다른 프로젝트에서 사용

```sh
uv build
# 다른 프로젝트에서:
uv add /path/to/devmrko_python_foundation-0.1.0-py3-none-any.whl
uv run foundation-new ../orders --package orders --database sqlite --auth session
```

생성 앱은 패키지 의존성으로 Foundation을 사용합니다. 배포 저장소를 구성하기 전에는 로컬 wheel을 설치하거나 uv의 경로 source를 명시해야 합니다. 생성기는 existing directory를 덮어쓰지 않습니다. 최소 health/ping/login 골격을 생성하며 Project 예제를 복사하지 않습니다. 업무 Entity·Repository·Service·migration은 소비 앱이 작성합니다.

wheel에는 python_foundation만 들어가고 example_app은 들어가지 않습니다. 소스 배포에는 예제·테스트·문서가 포함됩니다. 소비 앱의 uv.lock은 별도로 관리하고 Foundation 버전을 고정합니다. Oracle extra는 필요할 때만 설치합니다.

## 문서와 릴리스

공개 Python API의 계약은 docstring/type hint로, HTTP 계약은 OpenAPI/테스트로, 사용 절차와 결정 이유는 docs로 관리합니다. 릴리스마다 오류 코드·설정 키·DTO·의존성·마이그레이션 호환성을 검토합니다. GitHub 저장소와 Python 배포 저장소는 별개이며 PyPI 업로드는 아직 하지 않았습니다.

[FastAPI 동기/비동기](https://fastapi.tiangolo.com/async/) · [SQLAlchemy Session](https://docs.sqlalchemy.org/en/20/orm/session_basics.html) · [Oracle dialect](https://docs.sqlalchemy.org/en/20/dialects/oracle.html) · [PyJWT 검증](https://pyjwt.readthedocs.io/en/latest/usage.html) · [uv 프로젝트](https://docs.astral.sh/uv/concepts/projects/).
