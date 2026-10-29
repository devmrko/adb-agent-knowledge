# Python Foundation 설계

## 목적과 경계

Spring Foundation과 개발 방법론·HTTP 계약을 공유하는 독립 Python 라이브러리다. 저장소 python-foundation, 배포 이름 devmrko-python-foundation, import 이름 python_foundation. 한 배포 패키지와 실행 가능한 Project 예제를 제공한다. Python 3.12 이상, uv 잠금 파일, FastAPI/Pydantic/SQLAlchemy/Alembic을 사용한다.

첫 버전의 완료 범위는 오류 계약, Service 트랜잭션, CRUD API/HTML, session/token/mixed 인증, 설정 검증, HTTP 클라이언트, 요청 ID·JSON 로그, 생성기, wheel 독립 소비, CI·문서다. 영속 작업 엔진은 재구현하지 않으며 큐 adapter 계약과 별도 worker 지침을 제공한다. 실제 Oracle·인증 공급자·수집 서버 연결은 환경 검증으로 남긴다. 인프로세스 비동기 작업을 영속 작업으로 부르지 않는다.

## 계층·실행

Router → Service → Repository. Protocol로 계약을 정의하고 ABC로 공통 실행이 필요한 트랜잭션 경계를 제공한다. Router 상속은 요구하지 않는다. 동기 SQLAlchemy를 사용하는 경로는 def이며 FastAPI의 스레드 실행 경계를 사용한다. Session은 Service 호출의 with 블록 안에서 생성·커밋·롤백·종료하며 요청이나 task 간 공유하지 않는다. 중첩 서비스는 동일한 명시적 UoW를 전달해 하나의 트랜잭션을 사용한다. 전역 ContextVar를 통해 Session을 암묵적으로 전파하지 않는다. ORM Entity는 응답으로 직접 반환하지 않는다.

UnitOfWork는 성공 시 commit, 예외 시 rollback, 항상 close하며 진입·종료 정리 실패에도 연결을 반환한다. 조회용은 rollback 종료하고 ORM flush 변경을 거부한다. raw SQL의 read-only 강제나 독립 UoW 간 자동 REQUIRED 전파를 보장하지 않으며 문서에 한계를 명시한다. DB pool은 SQLAlchemy QueuePool 하나로 관리하고 Oracle driver pool과 중첩하지 않는다. SQLite 풀과 busy_timeout은 별도 설정한다.

## API 계약

/api/v1/projects: GET 목록 {items,page,size,total}, POST 201 + Location, GET/PUT /{id}, DELETE 204. DTO {id,name,version}, 수정은 name/version. 입력 오류 400, 없는 Project 404 PROJECT_NOT_FOUND, 낙관적 버전 충돌 409 PROJECT_VERSION_CONFLICT. ProblemDetail는 type/title/status/detail/code/requestId를 포함한다. 입력 원문·SQL·토큰·원인 메시지는 응답에 넣지 않는다. Python BusinessError(Exception)와 ErrorSpec을 사용한다. 정의는 enum 또는 상수로 재사용한다.

Java와 같은 업무 HTTP 계약 테스트를 이 저장소에 두고 base URL을 전달해 양쪽 실행 서버를 검증할 수 있게 한다. 인증 획득 방식은 별도 fixture다. Java 전용 작업 API의 동등성까지 주장하지 않는다.

## 인증과 권한

session은 서버측 SessionStore 포트에 무작위 세션 ID를 저장한다. 쿠키에는 사용자·권한·비밀번호를 담지 않는다. 개발 예제용 메모리 저장소는 단일 프로세스·재시작 로그아웃에 한정하고 운영 환경에서는 외부 저장소 구현을 요구한다. 로그인 전 CSRF 토큰, 로그인 시 ID 회전, 만료, 로그아웃 서버측 폐기를 제공한다. CSRF는 모든 session 변경 요청에 적용한다. 쿠키 HttpOnly/SameSite=lax, 운영 Secure 필수다.

token은 Bearer 전용, mixed는 /api/** token과 나머지 session을 분리한다. token 경로는 session/Basic을 대체 인증으로 쓰지 않는다. PyJWT로 RS256, HTTPS로 명시한 JWKS endpoint, issuer, API audience, exp, nbf, subject, typ=at+jwt를 검증한다. 스코프는 SCOPE_ authority로 변환하고 업무 roles는 기본 신뢰하지 않는다. 검증 키 조회는 동기 dependency에서 수행하고 event loop를 막지 않는다. 키·토큰 오류는 안전한 401이며 인증 발급 서버는 만들지 않는다. OIDC/opaque는 후속 adapter 범위다.

Actor는 issuer/subject/authorities를 가진 불변 객체. 기능 권한 dependency와 Service 정책 포트를 제공한다. 예제는 공유 작업 공간이며 자원별 소유권·테넌트 격리를 구현하지 않는다.

## 운영·재사용

Pydantic Settings로 잘못된 pool/timeout/auth 설정을 기동 시 거부. 안전한 JSON 로그와 서버가 생성한 요청 ID, 클라이언트에 안전한 500. HTTPX sync/async client에 시간 제한·연결 제한·close 계약 제공, 자동 retry는 하지 않는다. Graceful shutdown에서 engine/client를 닫는다. SQLAlchemy metadata.create_all은 테스트에만 허용하고 실행 앱은 Alembic migration을 명시적으로 적용한다.

uv build로 wheel/sdist 생성. 별도 가상환경에 wheel만 설치해 예제 및 생성 앱의 import/기동·트랜잭션을 검증한다. 템플릿은 기존 디렉터리를 덮어쓰지 않는다. 라이브러리/소비 앱의 잠금 파일은 독립적이며 자동 최신 버전을 추종하지 않는다.

## 개발 방법론과 검증

설계 → 구현 → Ruff/타입 검사 → 계약·통합 테스트 → 실제 프로세스·wheel 소비 → 문서/변경 이력 → Git 커밋·비공개 GitHub 반영. 테스트는 commit/rollback/commit 실패 정리/권한 거부/CSRF/세션 회전·폐기/잘못된 JWT/버전 충돌/500 비노출/HTML escaping/마이그레이션을 포함한다. Python final은 정적 검사 약속이며 Java처럼 런타임 재정의를 막는 장치가 아님을 문서화한다.
