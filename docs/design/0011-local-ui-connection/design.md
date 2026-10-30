# 로컬 개발 화면 자동 연결

> 설계 당시의 결정·계획을 보존한 기록입니다. 현재 기본값·설치·지원 범위는 [현재 매뉴얼](../../README.md)을 기준으로 확인하세요. 이 문서의 계획이나 과거 검증은 현재 구현·배포 보장이 아닙니다.

사용자 요청: localhost 검색 화면에서 토큰을 매번 입력하지 않는다.
UI_AUTO_CONNECT=true(기본), development, DevelopmentVerifier, loopback API_HOST일 때만 제공한다.
POST /knowledge/local-connection은 loopback peer + 허용된 localhost Host + 동일 Origin +
Sec-Fetch-Site=same-origin + X-Knowledge-UI=1을 모두 확인하고 기존 개발 토큰을 반환한다.
새 토큰/세션을 발급하지 않으며 응답 no-store. CORS를 열지 않는다. cross-origin과 DNS rebinding
Host는 거부한다. production/외부 bind에서는 404이고 기존 Bearer 인증은 그대로 유지한다.
화면은 로드 시 한 번 자동 연결을 시도하고 불가하면 기존 수동 입력을 사용한다.
브라우저 저장소/쿠키/URL에는 토큰을 보관하지 않는다. 이 기능은 로컬 OS 사용자를 신뢰하는 개발 편의다.
