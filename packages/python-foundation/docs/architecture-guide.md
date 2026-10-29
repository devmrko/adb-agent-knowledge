# 공통 프레임워크를 설계할 때의 판단 기준

이 문서는 패턴 이름을 외우기 위한 사전이 아니라, 새 프로젝트의 기반을 기획할 때 무엇을 결정해야 하는지 살펴보는 안내서입니다. Java와 Python에 같은 질문을 적용하되 구현 수단은 언어에 맞게 선택합니다. 아래의 **설계 후보는 구현 완료 목록이 아닙니다.** 저장소별 구현 상태는 마지막 절에 구분합니다.

## 1. 패턴보다 먼저 정할 것

먼저 주요 사용자와 업무, 데이터의 소유자, 허용 지연 시간, 예상 동시 사용자, 데이터 유실 허용 여부, 운영 인력과 비용을 적습니다. 평균 응답 시간만 보지 말고 p95/p99, 최대 처리량, 오류율, 복구 목표도 정합니다. 요구 수치가 없으면 비동기·캐시·분산 시스템의 필요성을 판단하기 어렵습니다.

| 설계 질문 | 기본 선택과 전환 조건 |
| --- | --- |
| 무엇을 공통으로 만들까? | 오류 계약·트랜잭션 실행·인증 연결·설정 검증 등 반복되는 기술 규칙. 업무 Entity·권한 정책·스키마는 앱 소유 |
| 어디까지 나눌까? | 하나의 배포 단위 안에서 책임을 구분하는 모듈형 모놀리스부터. 독립 배포·격리·확장이 필요할 때 서비스 분리 |
| 어디에 확장 지점을 둘까? | 실제로 교체할 인증 공급자·저장소·외부 시스템 경계. 모든 클래스에 인터페이스와 팩토리를 만들지는 않음 |
| 공통 변경이 앱을 깨뜨리지 않을까? | 공개 API·HTTP 계약·설정 키·DB 마이그레이션을 버전 관리하고 이전 버전 소비 앱으로 호환성 확인 |
| 선택 기능의 기본값은? | 명시적 활성화, 잘못된 필수 설정은 시작 시 실패. 활성화되지 않은 기능을 동작하는 것처럼 보이게 하지 않음 |

## 2. 구조·의존성과 재사용

| 개념 / 패턴 | 해결하려는 문제 | 적용 기준과 주의점 |
| --- | --- | --- |
| MVC | 입력 처리, 업무 데이터, 화면 표현의 혼재 | Controller는 요청을 받아 Service를 호출하고 View/JSON을 반환. Service와 Repository는 MVC를 구현할 때 추가로 나눈 업무·저장 책임 |
| Layered Architecture | 웹 변경이 DB 코드까지 번지는 문제 | Controller/Router → Service → Repository. 인증된 사용자와 DTO를 전달하고 HTTP 객체를 업무 코드 전체에 퍼뜨리지 않음 |
| Ports & Adapters | 업무 코드가 특정 공급자 SDK에 묶임 | 업무에 필요한 계약을 Port로, DB·인증·HTTP 구현을 Adapter로 둠. 단순 CRUD에 거대한 계층을 강요하지 않음 |
| Interface / Protocol | 호출자가 구현 세부사항까지 알아야 함 | 기능 계약을 먼저 정의. Java는 명시적 implements, Python Protocol은 구조적 타입 계약이며 타입 검사기로 확인 |
| Abstract Class / Template Method | 실행 때마다 지켜야 할 순서가 누락됨 | 기반이 시작 → 업무 실행 → 정리 흐름을 소유하고 업무 부분만 구현. 상속 계층은 얕게 유지 |
| DI / IoC | 객체가 의존 구현을 직접 생성하여 교체·테스트가 어려움 | 생성자/함수 인자로 필요한 객체를 받음. 조립은 앱 시작 지점에 집중. DI는 상속이 아니며 DI 컨테이너 없이도 가능 |
| Strategy | 정책별 if 분기가 곳곳에 반복됨 | 인증 방식·권한 정책 등 교체 가능한 동작을 같은 계약으로 제공. 호출 시점과 선택 기준은 별도로 명확히 정의 |
| Adapter / Facade | 외부 API 형태와 내부 계약이 다름 / 사용 절차가 복잡함 | Adapter는 형식을 변환, Facade는 사용 진입점을 단순화. 외부 오류·데이터를 내부 계약으로 변환 |
| Factory / Composition Root | 객체 조립과 업무 실행이 섞임 | 앱 시작 시 설정에 맞는 구현들을 연결. Factory는 생성 규칙이 복잡하거나 생성 시점 제어가 필요할 때 사용 |

SOLID는 이 선택을 점검하는 기준입니다. 변경 이유별 책임 분리(SRP), 필요한 확장 지점(OCP), 대체 가능한 구현 계약(LSP), 작은 소비자별 계약(ISP), 구체 기술 대신 계약에 의존(DIP)을 확인합니다. 클래스 수를 늘리는 목표가 아닙니다.

## 3. AOP와 공통 처리의 위치

로깅·계측·권한·트랜잭션 같은 여러 기능에 걸친 규칙을 어디에 적용할지가 핵심입니다.

| 적용 위치 | 잘 맞는 일 | 놓치기 쉬운 점 |
| --- | --- | --- |
| HTTP Filter / Middleware | 요청 ID, 요청 크기 제한, HTTP 인증 처리 | 배치·이벤트 소비·직접 Service 호출에는 적용되지 않음 |
| AOP Proxy / Decorator | 메서드 호출 전후 권한·계측 등 | 감싸는 경로를 우회하면 규칙이 빠질 수 있음. 예외·반환형·동기/비동기 동작 보존 필요 |
| Template Method / Context Manager | 트랜잭션·자원 수명처럼 반드시 닫아야 하는 경계 | 기반 진입점이나 with 블록을 실제로 사용해야 보장됨 |
| 명시적 업무 정책 호출 | 소유권, 승인 단계, 금액별 권한 | 업무 의도를 드러내야 하므로 모두 숨겨진 공통 처리로 옮기지 않음 |

Spring AOP는 주로 프록시 기반이므로 같은 객체 내부의 self-invocation은 프록시 조언을 우회합니다. 클래스 프록시의 final 메서드도 조언 대상이 될 수 없습니다. **이 Java 기반의 트랜잭션은 final execute 안의 TransactionTemplate으로 직접 실행하므로 @Transactional 프록시에 의존하지 않습니다.** [Spring 공식 설명](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)

Python에서도 데코레이터·미들웨어·컨텍스트 매니저로 공통 규칙을 분리할 수 있습니다. 다만 Spring AOP와 동일한 자동 프록시 체계를 제공한다는 뜻은 아닙니다. 중첩 순서, 취소 시 정리, 인증 실패 시 업무 미실행을 명시적으로 검증해야 합니다.

## 4. 데이터 모델·트랜잭션·동시 수정

| 설계 질문 | 패턴 / 선택 | 선택 기준과 실패 시나리오 |
| --- | --- | --- |
| API 데이터와 저장 데이터를 같이 쓸까? | DTO / Data Mapper | Entity의 내부 필드·지연 로딩·변경 가능성을 HTTP에 노출하지 않음. Java record, Python Pydantic 모델을 경계에 사용 |
| 어디서 commit할까? | Service Transaction / Unit of Work | 한 업무의 여러 Repository 작업을 함께 commit/rollback. Repository는 스스로 commit하지 않음 |
| 서비스가 서비스를 부르면? | Transaction Propagation / 명시적 UoW 전달 | 독립 commit인지 같은 원자성인지 먼저 결정. Java REQUIRED와 Python의 독립 with 블록은 같은 동작이 아님 |
| 동시에 같은 데이터를 수정하면? | Optimistic Lock / Pessimistic Lock | 일반 수정은 버전 검사·충돌 응답. 경합이 높고 배타 처리가 필수인 경우 잠금 비용과 교착까지 검토 |
| 중복·참조 무결성은 어디서 보장할까? | DB Constraint + 업무 검증 | 사전 조회만으로 동시 생성 경쟁을 막을 수 없음. unique/FK 제약과 오류 변환을 함께 설계 |
| ORM이면 DB를 자유롭게 바꾸나? | Repository / Dialect | 타입·정렬·잠금·DDL·페이지 처리 차이는 남음. Oracle/SQLite 각각 실제 통합 검증 필요 |
| 조회가 느리면? | Projection / Fetch Plan / Pagination | N+1, 인덱스, 실행 계획, 최대 페이지 크기부터 확인. 읽기·쓰기 요구가 크게 다를 때 CQRS 검토 |
| 캐시를 넣을까? | Cache-Aside | 허용 가능한 데이터 지연·무효화·동시 만료·테넌트별 키를 먼저 결정. 권한 결과 캐시는 권한 변경 반영까지 설계 |
| DB와 이벤트를 동시에 기록하면? | Transactional Outbox / Inbox | 업무 변경과 발행 의도를 같은 DB 트랜잭션에 기록. 별도 발행자와 소비자 중복 제거 필요 |
| 여러 서비스의 업무를 묶으면? | Saga / Process Manager | 분산된 단계와 보상·수동 복구를 관리. 단일 DB 트랜잭션으로 충분하면 도입하지 않음 |

Outbox는 DB 저장과 메시지 발행 사이의 이중 쓰기 실패를 다루는 패턴입니다. 발행 중복 가능성까지 고려해야 합니다. 두 저장소의 현 상태를 Outbox 구현으로 해석하면 안 됩니다. [AWS 설계 안내](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html)

## 5. Async: 무엇을 기다리지 않을 것인가?

비동기는 하나의 기능이 아닙니다. **요청 안에서 I/O를 겹쳐 처리하기**, **응답 후 작업하기**, **재시작 후에도 작업을 이어가기**는 서로 다른 요구입니다. DB 풀이 동기여도 작업을 별도 실행기로 넘겨 요청 스레드를 반환하거나 독립 I/O를 겹치는 이점이 있습니다. 다만 DB의 처리 용량이 늘거나 트랜잭션이 자동 전달되지는 않습니다.

| 요구 / 질문 | 관련 패턴 | 설계할 항목 |
| --- | --- | --- |
| 독립된 외부 호출을 함께 기다릴까? | Fan-out/Fan-in / Structured Concurrency | 전체 시간 예산, 일부 실패 허용 여부, 형제 작업 취소, 결과 합치기. DB 트랜잭션을 잡은 채 느린 외부 호출을 기다리지 않음 |
| 동기 DB를 쓰면서 요청을 처리할까? | Worker Pool / Bulkhead | 스레드 실행과 동시성 제한. 작업마다 독립 Session/트랜잭션. 워커 수·DB 풀·대기열을 함께 산정 |
| 응답 후 재시작해도 실행해야 하나? | Durable Queue / Producer–Consumer | 저장 완료 후 접수 응답, 작업 ID·상태 조회, 종료 중 drain, 재시작 복구, 보존 기간 |
| 한 번 더 실행되면 위험한가? | Idempotent Consumer / Deduplication | 멱등 키의 사용자·업무 범위, 입력 일치 검사, 보관 기간. DB 변경과 외부 부작용 각각 검토 |
| 워커가 죽거나 멈추면? | Lease / Fencing / State Machine | 임대 만료, 오래된 워커의 결과 쓰기 방지, 합법적인 상태 전이. 외부 시스템도 fencing을 이해해야 외부 부작용까지 차단 가능 |
| 과부하·장애가 지속되면? | Backpressure / Bounded Queue / Dead Letter | 대기열 상한, 수락 거절, 최대 재시도, 운영자 재처리. 무제한 큐로 메모리와 DB를 소모하지 않음 |
| 취소되면 실행도 멈추나? | Cooperative Cancellation / Deadline | 응답 연결 종료와 실제 작업 종료는 별개. 동기 DB 호출·이미 실행된 외부 부작용은 자동 취소되지 않음 |

FastAPI의 일반 def 경로 함수는 스레드풀에서 실행됩니다. 반면 async def 내부에서 직접 호출한 동기 함수는 자동으로 스레드풀로 이동하지 않습니다. 동기 DB 작업 전체를 적절한 실행 경계로 옮겨야 합니다. CPU 중심 작업은 별도 프로세스/작업 시스템도 검토합니다. [FastAPI 실행 방식](https://fastapi.tiangolo.com/async/)

Python TaskGroup은 관련 작업의 수명을 묶을 때 유용합니다. 취소를 무심코 삼키면 정리가 깨질 수 있습니다. 이것은 영속 작업 큐를 대신하지 않으며 현재 공통 기반에 TaskGroup 실행기가 구현되어 있다는 뜻도 아닙니다. [Python 작업·취소 문서](https://docs.python.org/3/library/asyncio-task.html)

## 6. Security: 인증 이후의 설계까지

보안 설계는 “JWT를 사용할까?”보다 먼저 신뢰 경계, 보호할 자산, 호출자 유형, 권한 변경·탈퇴·자격 증명 탈취 시 동작을 정해야 합니다. 인증은 누구인지, 인가는 해당 작업을 그 데이터에 수행해도 되는지를 판단합니다.

| 설계 질문 | 패턴 / 구조 | 적용 기준 |
| --- | --- | --- |
| 세션·토큰 공급자를 교체하려면? | Strategy + Adapter | 인증 결과를 공통 Actor로 변환. 인증 방식은 앱·경로 설정, 업무별 권한은 엔드포인트와 Service 정책에서 선택 |
| 여러 보안 단계를 어떤 순서로? | Chain of Responsibility / Middleware Chain | 경로 선택 → 인증 → CSRF 등 요청 검증 → 권한 판단 → 업무. 실패하면 다음 업무 처리를 차단하고 체인 순서를 검증 |
| 권한 판단을 어디서 실행할까? | Policy Enforcement Point / Policy Decision Point | 진입점에서 강제하고 정책 객체에서 판단. 초기에는 같은 프로세스에서 분리하면 충분하며 외부 정책 서버는 선택 사항 |
| 역할만으로 충분할까? | RBAC / ABAC / ReBAC | 역할은 기능 접근, 속성은 테넌트·소유권·상태·금액, 관계는 소유자·팀·공유 관계. 복잡도에 맞춰 선택 |
| 복잡한 조건을 재사용하려면? | Policy / Specification / Composite | 작은 조건을 AND/OR로 조합하되 기본 거부와 정책 충돌 규칙을 명확히 함. 오류 시 허용으로 바꾸지 않음 |
| ID를 바꿔 다른 사람 데이터를 볼 수 있나? | Resource-scoped Authorization | 조회·수정·목록·작업 상태 조회마다 대상 리소스와 테넌트를 확인. ROLE_USER 확인만으로 소유권은 보장되지 않음 |
| HTTP 외에도 호출되면? | Service-level Guard / Defense in Depth | 배치·큐·직접 호출에서도 필요한 업무 권한 검사. Controller 기반 클래스 상속 자체는 접근 통제가 아님 |
| 작업 큐로 사용자를 넘기면? | Explicit Security Context / 최소 권한 서비스 계정 | 토큰 원문이나 요청 객체를 저장하지 않음. 접수 시와 실행 시 권한 확인 기준, 사용자 탈퇴·권한 회수 시 처리 결정 |
| 토큰·세션을 어떻게 폐기할까? | Server-side Session / Token Lifecycle | 세션 회전·만료·로그아웃·공유 저장소. JWT는 서명뿐 아니라 issuer/audience/유효기간/종류 검증 및 키 회전·회수 지연 고려 |
| 브라우저와 외부 클라이언트가 같이 쓰면? | 명시적 인증 경계 | 쿠키 기반 상태 변경은 CSRF 방어. CORS는 인증 수단이 아님. 토큰 경로에 세션 인증이 우연히 대체 적용되지 않도록 테스트 |

기본 거부, 매 요청 권한 확인, 리소스별 권한 검증을 기준으로 삼습니다. 기능 단위 권한과 소유권 검사는 별개의 계약입니다. [OWASP 인가 지침](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)

추가로 비밀 설정의 외부 주입·회전, TLS, 쿠키 속성, HTML 출력 이스케이프와 CSP, SQL 매개변수화, 외부 URL의 SSRF 방어, 로그인 시도 제한, 파일 업로드 크기·형식·저장 위치를 검토합니다. 보안 감사 로그는 일반 디버그 로그와 목적·보존·접근 권한을 구분하며 비밀번호·토큰·민감 개인정보를 기록하지 않습니다. 이러한 통제를 공통 기반이 전부 제공한다고 가정하지 않습니다.

## 7. 오류·외부 연동·회복력

| 설계 질문 | 패턴 / 선택 | 판단 기준 |
| --- | --- | --- |
| 업무 실패를 어떻게 표현할까? | Typed Exception / Error Catalog | 업무 오류 코드·분류·안전한 메시지를 정의. 예외 타입은 호출자가 다르게 처리해야 할 때 구분하며 모든 코드마다 클래스를 만들 필요는 없음 |
| HTTP 응답으로 누가 바꿀까? | Exception Translator / Problem Details | Service는 업무 오류를 던지고 경계에서 상태 코드로 변환. 원인은 내부에 보존하되 SQL·공급자 원문은 응답에 노출하지 않음 |
| 잠시 실패하면 다시 호출할까? | Retry + Exponential Backoff + Jitter | 일시적 오류이면서 멱등하거나 중복 제어 가능한 요청에만 횟수·총 시간 제한을 두고 적용. 인증 오류·업무 거절은 무조건 재시도하지 않음 |
| 외부 장애가 전체로 번지면? | Timeout / Circuit Breaker / Bulkhead | 연결·응답·전체 시간 예산, 동시 호출 제한, 회로 복구 조건. 재시도 중첩으로 호출량이 폭증하지 않도록 책임 한 곳에 배치 |
| 외부 데이터가 내부로 스며들면? | Anti-Corruption Layer | 공급자 모델·코드·오류를 내부 의미로 변환. 단순 HTTP 래퍼와 업무 의미 변환 계층을 구분 |

Java의 RuntimeException은 checked exception 선언 없이 전파됩니다. Python에는 Java 같은 checked/unchecked 구분이 없으므로 업무 예외는 Exception 하위 타입으로 정의하면 됩니다. 어느 쪽이든 예외를 던지는 것만으로 재시도·권한·트랜잭션 정책이 모두 생기지는 않습니다.

## 8. 운영·테스트·배포도 설계의 일부

| 영역 | 기획 때 정할 내용 | 검증 예 |
| --- | --- | --- |
| 관측성 | 요청/작업 상관 ID, 구조화 로그, 메트릭, 분산 추적, 민감 정보 제거 | 작업 경계를 넘어 실패 원인을 찾을 수 있는지, 고유 사용자 ID를 메트릭 라벨로 남발하지 않는지 |
| 상태 점검 | liveness와 readiness 구분, 의존 시스템 장애 시 수락 여부 | DB 장애 시 필요한 준비 상태 변화. 단일 health API만으로 모든 상태가 해결되지는 않음 |
| 자원 수명 | 시작/종료 훅, 풀 정리, 진행 중 작업 drain, 최대 종료 시간 | 종료 신호 중 요청·작업의 완료 또는 안전한 재처리 |
| 검증 전략 | 업무 단위·DB 통합·공급자 계약·HTTP·아키텍처 테스트 | 권한 우회, 중복 처리, 동시 수정, rollback, 큐 포화, 타임아웃, 장애 복구 |
| 설정 | 타입 검증, 환경별 설정, 비밀 분리, 잘못된 설정의 조기 실패 | 운영에서 개발용 세션 저장소나 기본 비밀번호가 활성화되지 않는지 |
| 스키마 변경 | 앱 소유 마이그레이션, Expand–Contract, 백업·복구 | 구버전/신버전 앱이 함께 실행되는 동안 호환되는지. DB 변경은 코드 rollback만으로 되돌아가지 않음 |
| 공급망·배포 | 의존성 고정, 취약점·라이선스 점검, 재현 빌드, 아티팩트 저장소 | 소스 경로 없이 배포 JAR/wheel을 소비하는 새 앱의 실행 |
| 문서·버전 | ADR, 사용법, 공개 API 계약, 변경 이력, 폐기 일정 | 구현 상태와 설계 후보 분리. Java Javadoc / Python docstring·타입, HTTP OpenAPI를 함께 관리 |

## 9. 새 기능을 추가할 때의 짧은 의사결정 기록

1. **요구와 실패:** 누가 어떤 데이터를 다루며, 지연·중복·유실·권한 위반 중 무엇이 허용되지 않는가?
2. **경계:** HTTP, Service, DB, 외부 시스템, 작업 큐 중 책임과 원자성을 어디까지 묶는가?
3. **대안:** 가장 단순한 구현과 추가 패턴 도입의 비용을 비교했는가?
4. **계약:** 입력·출력·오류·권한·트랜잭션·취소·재시도 규칙은 무엇인가?
5. **검증:** 정상 흐름 외에 장애·경합·직접 호출·재시작으로 우회되는 경로를 확인했는가?
6. **운영과 재사용:** 관측·복구·설정·버전 호환·소비 앱 적용 방법을 설명할 수 있는가?

이 순서로 ADR에 선택 이유를 남깁니다. 필요하지 않은 패턴을 도입하지 않는 것도 설계 결정입니다.

## 10. Python Foundation에 적용해서 읽기

Python에서도 위 설계와 패턴을 사용할 수 있습니다. Java의 클래스 구조를 그대로 복사하기보다는 Protocol·ABC·함수 주입·with·미들웨어로 필요한 보장을 만듭니다. 아래는 현재 코드 기준입니다.

| 영역 | 현재 구현 / 적용 위치 | 추가 설계·구현이 필요한 범위 |
| --- | --- | --- |
| MVC에 대응하는 계층 | FastAPI Router → ProjectService → Repository, Jinja2 화면, Pydantic DTO | FastAPI 자체가 Spring MVC는 아님. 업무 모델과 UI는 앱 소유 |
| DI / Factory | create_app에서 설정·Security·DB·Service 조립, Depends(current_actor)로 요청 사용자 주입 | Spring Bean 자동 탐색이나 같은 수명 규칙을 가정하지 않음 |
| Protocol / ABC | UnitOfWork·SessionStore·TokenVerifier 등의 계약, AbstractUnitOfWork의 공통 종료 흐름 | Protocol은 구조적 정적 계약이며 런타임 입력 검증 기능이 아님 |
| 트랜잭션 / ORM | Service의 with UoW, SQLAlchemy Repository, QueuePool, 버전 충돌 감지 | 중첩 Service는 활성 UoW를 명시적으로 전달해야 같은 트랜잭션. Oracle 실제 검증은 별도 |
| 인증 / 정책 | session/token/mixed 선택, JWT 검증, Actor 권한 검사, AuthorizationPolicy 계약 | 정책 계약만으로 소유권·테넌트 격리가 구현되지 않음. 운영 공유 SessionStore·사용자 인증은 앱 제공 |
| 공통 처리 | ASGI 요청 ID 미들웨어, 예외 핸들러, with 기반 정리 | 범용 AOP 프록시·범용 보안 데코레이터 엔진은 미구현 |
| 비동기 | 동기 DB 경로 함수는 def, 동기/비동기 HTTPX 호출 도구 | DurableJobs는 Protocol과 접수 데이터만 있음. 영속 큐·워커·복구·Outbox·TaskGroup 실행기는 미구현 |
| 오류 / 운영 | ErrorSpec + BusinessError, 안전한 HTTP 오류, 요청 ID·JSON 로그, DB health | 자동 retry·circuit breaker·전체 추적·감사 저장소는 별도 설계 |
| 재사용 / 검증 | 단일 wheel, 프로젝트 생성기, uv.lock, Ruff·mypy·pytest, 독립 wheel 소비 검증 | PyPI 배포와 실제 운영 인증 공급자·Oracle 검증은 별도 |

install_web을 호출하는 것만으로 모든 경로가 자동 보호되지는 않습니다. 보호할 경로는 Depends 등 인증 의존성을 선언하고, 업무에 필요한 권한도 확인해야 합니다. MemorySessionStore는 개발용 단일 프로세스 저장소입니다. 예제는 공유 작업 공간이며 사용자별 소유권 격리를 제공하지 않습니다.

읽기 전용 UoW는 ORM 변경 flush를 막지만 DB 권한이나 임의 raw SQL 쓰기까지 차단하는 보안 경계가 아닙니다. Session/UoW는 작업마다 생성하며 여러 스레드·태스크에서 공유하지 않습니다.

### 코드와 기존 문서로 연결

- [database.py](../src/python_foundation/database.py): Protocol, ABC, Template Method, Context Manager, Unit of Work의 결합.
- [security.py](../src/python_foundation/security.py): 사용자 표현, 인증 구현 교체 계약, 요청별 의존성.
- [web.py](../src/python_foundation/web.py): Middleware와 예외 응답 변환의 적용 범위.
- [app.py](../example_app/app.py), [service.py](../example_app/service.py), [repository.py](../example_app/repository.py): 객체 조립과 Router → Service → Repository 흐름.
- [jobs.py](../src/python_foundation/jobs.py): 영속 작업의 미구현 계약 범위.
- [설계](design/foundation.md), [사용법](how-to.md), [검증 결과](validation.md), [Java의 대응 설계](https://github.com/devmrko/spring-foundation/blob/main/docs/architecture-guide.md).

### Java와 대응하는 수단을 고르는 법

| 원하는 보장 | Python 수단 | 선택 기준 |
| --- | --- | --- |
| 구현을 교체할 수 있는 계약 | Protocol | 필요한 메서드의 구조를 정의하고 mypy 등으로 검사. 명시적 상속은 필수가 아님 |
| 공통 구현과 필수 구현 지점 | ABC + abstractmethod | 수명·정리 순서를 재사용할 때 사용. 모든 Service에 ABC를 만들지는 않음 |
| 외부 의존성 전달 | 생성자/함수 인자, Depends | 서비스 조립과 요청별 인증을 구분. 전역 객체 조회인 Service Locator에 의존하지 않음 |
| 함수 전후 처리 | decorator | 호출 의미·타입·예외를 보존. async 함수는 async 실행을 감싸야 하며 실제 await 이전에 정리를 끝내면 안 됨 |
| HTTP 전후 처리 | ASGI middleware | HTTP에 공통인 규칙. Service 직접 호출에 필요한 보장은 별도 |
| 성공/실패와 무관한 정리 | context manager / with | Session·트랜잭션·클라이언트 수명을 명시. 현재 UoW가 사용하는 방식 |
| 타입이 있는 데이터 | dataclass / Pydantic | 내부 값 객체와 외부 입력 검증을 구분. dict는 구조가 동적일 때 사용 |
| 업무 예외 | Exception 하위 BusinessError | Java의 RuntimeException과 목적은 대응하지만 Python에는 checked exception 구분이 없음 |

[Python Protocol 공식 문서](https://docs.python.org/3/library/typing.html#typing.Protocol)와 [FastAPI DI 공식 문서](https://fastapi.tiangolo.com/tutorial/dependencies/)를 함께 읽으면 언어의 계약과 프레임워크의 요청별 의존성 처리를 구분하기 쉽습니다.
