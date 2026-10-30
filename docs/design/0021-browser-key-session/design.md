# 같은 HTTPS 도메인의 노트 UI와 API 키 세션

> 설계 당시의 결정·계획을 보존한 기록입니다. 현재 기본값·설치·지원 범위는 [현재 매뉴얼](../../README.md)을 기준으로 확인하세요. 이 문서의 계획이나 과거 검증은 현재 구현·배포 보장이 아닙니다.

2026-10-20 사용자 승인: knowledge.example.com의 /knowledge, /knowledge-assets/, /api/v1/를 지식 서비스로 라우팅하고 API 키를 한 번 입력해 로그인 상태를 유지한다. 기존 /v1 모델 API는 유지한다.

## 인증 계약

모델 API의 앱별 키는 개인 노트에 대한 권한을 부여하지 않는다. 별도 노트 전용 키의 SHA-256 해시를 WEB_API_KEY_SHA256으로 설정하고 서버에서 상수 시간 비교한다. 키는 로그인 요청에만 전송하며 브라우저 localStorage/sessionStorage나 쿠키에 저장하지 않는다. WEB_ACTOR_ISSUER/SUBJECT는 키에 허용된 소유자이며 현재 개인 저장소의 local-development/developer와 일치시킨다. 사용자 자동 생성이나 다른 모델 키의 권한 승격은 없다.

POST /knowledge/session: JSON api_key와 정확한 Origin 및 X-Knowledge-UI: 1 필요. 검증 후 256비트 무작위 세션을 발급하고 기존 쿠키 세션을 회전한다. __Host-vk_session 쿠키는 Secure/HttpOnly/SameSite=Strict/Path=/, 기본 TTL 7일(최대 30일). 서버 SQLite 세션 저장소에는 세션 ID 해시, CSRF 토큰, 키 해시, 만료만 보관한다. 파일은 0600, 부모 디렉터리 0700. 같은 서버의 여러 프로세스와 재시작에 사용 가능하며 다중 호스트 공유 저장소는 아니다. 키 회전이나 actor 변경 시 기존 세션을 무효화한다. GET /knowledge/session은 로그인 상태 및 CSRF를 반환한다. DELETE는 CSRF+Origin 검증 뒤 세션을 삭제한다.

기존 /api/v1 Bearer 인증은 유지한다. Authorization 헤더가 있으면 Bearer 검증만 하고 실패를 쿠키로 우회하지 않는다. 헤더가 없을 때만 유효 쿠키를 허용하며 변경 요청(검색 POST 포함)은 Origin+CSRF를 요구한다. 공개 배포에서는 UI_AUTO_CONNECT=false, Nginx /knowledge/local-connection 404. 공개 Origin은 https의 고정 origin이며 쿠키 요청의 Host/Scheme도 확인한다. 모델 API와 다른 쿠키 이름을 쓰고 Secure host-only 쿠키로 범위를 제한한다. Nginx 로그인 속도 제한을 적용한다.

## 화면과 검증

새로고침 시 세션을 조회하고 목록을 복원한다. 키 입력 후 즉시 입력값을 지우고 세션/CSRF만 사용한다. 로그아웃 실패 시 성공으로 표시하지 않는다. 기존 비공개 로컬 개발 모드의 토큰 경로는 유지한다. API 키 유효/무효, 쿠키 옵션, 세션 회전/만료/재시작/로그아웃, Origin/CSRF, Bearer+cookie 우선순위, 소유자 격리, 비활성 모드를 테스트한다. 기존 전체 ruff/format/mypy/pytest를 실행하고 실제 HTTPS의 인증 경계 및 브라우저 로그인을 검증한다.
