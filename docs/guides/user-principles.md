# 사용자 원칙: 검색 순위와 관계없이 매 요청에 적용

[English](user-principles.en.md)

존댓말, 해결 중심, 쉬운 설명처럼 반드시 참고할 선호를 벡터 검색 결과에 맡기지 않습니다.
인증된 사용자 설정으로 Oracle에서 정확 조회하고, 매 요청의 기억 확인 훅이 별도 영역에
전달합니다. Kev가 `skip`을 반환하거나 민감한 요청의 검색을 생략해도 활성 원칙은 전달합니다.
전달을 보장하는 훅과 모델이 실제 지키는 것은 다릅니다. 상위 지침과 현재 사용자의 명시적
요청이 우선하며 원칙은 도구 권한을 부여하지 않습니다. 훅이 없는 클라이언트에는 자동 적용되지 않습니다.

## 웹 관리

1. `/knowledge`에 로그인하고 **사용자 원칙 · 매 요청에 적용**을 엽니다.
2. **저장된 원칙 불러오기**를 누릅니다. 처음에는 빈 목록입니다.
3. 기본 6개 초안을 추가하거나 직접 작성합니다. 추천 3개는 사용자가 선택합니다.
4. 제목·적용 문구·활성화·순서·범위(`global` 또는 `project:이름`)를 수정합니다.
5. 적용 문구 미리보기에서 프로젝트 범위와 문장을 확인합니다.
6. 변경 이유를 입력하고 **승인하고 적용**합니다. 지원되는 훅의 다음 요청부터 읽습니다.

기본 6개: 존댓말, 해결 중심, 행동 전 계획, 단순한 접근, 오류 인정·개선, 쉬운 설명.
추천 후보: 확인 수준 구분, 기존 맥락 유지, 완료 확인. 모든 사용자에게 자동 설치하지 않습니다.
초안 작성이나 모델의 추천만으로는 저장·활성화되지 않습니다. 번역·LLM 문구 보강도 자동 수행하지 않습니다.
나중에 추가하더라도 원문/제안 비교와 사용자 승인을 거쳐야 합니다.

전체 최대 20개, 개별 적용 문구 600자, 총 적용 문구 6000자입니다. 활성 원칙은 임의 top-k로
잘리지 않습니다. 전역과 선택한 프로젝트 원칙은 순서대로 함께 전달되며 프로젝트 원칙이
자동으로 전역을 덮어쓰지는 않습니다. 모순은 웹에서 정리하세요. 짧고 검증 가능한 문장을 권합니다.

## 저장·인증·이력

`vk_principle_bundle`은 현재 버전, `vk_principle_revision`은 변경 당시 전체 원칙과 변경 이유,
인증된 사용자 식별자·시간을 저장합니다. `vk0014` 마이그레이션으로 생성됩니다.
버전 충돌 시 409이며 오래된 화면의 덮어쓰기를 막습니다. 원칙 제거도 새 버전이며 과거 이력은
남습니다. 애플리케이션 쓰기와 이력은 같은 트랜잭션입니다. 직접 SQL 변경용 감사 트리거는
이 기능에 포함되지 않습니다. 기존 노트는 조회 전용이며 원칙 편집만 웹 쓰기를 허용합니다.

브라우저는 기존 API 키 로그인·HttpOnly 세션 쿠키·CSRF 검사를 사용합니다. Bearer API는
그 토큰의 사용자로 동작합니다. 같은 계정의 키를 여러 사람에게 공유하면 같은 원칙을 편집합니다.
승인은 인증된 요청의 명시적 표시이며 사람이 직접 클릭했다는 암호학적 증명은 아닙니다.
MCP에는 원칙 쓰기 도구를 추가하지 않았습니다.

## 설치·업데이트 순서

1. API/MCP 서버 코드를 업데이트하고 `./.venv/bin/alembic upgrade head`로 테이블을 준비합니다.
2. API를 다시 시작합니다. 기존 MCP 연결은 새 코드로 재연결합니다.
3. 클라이언트의 `scripts/memory_prompt_hook.py`를 업데이트합니다. 기존
   [훅 설치](required-memory-hook.md) 설정을 사용합니다. 호스트가 변경된 명령의 재승인을 요구하면 검토·승인합니다.
4. 웹에서 원칙을 승인하고, 실제 요청의 전달 문구와 `principle_version` 감사 필드를 확인합니다.

새 훅은 `knowledge_decide(principle_scopes=[...])`에 추가된 `user_principles` 응답을 요구합니다.
서버가 오래됐거나 조회가 실패하면 정상 원칙으로 가장하지 않고 요청을 차단합니다.
서버를 먼저 업데이트하세요. 새 MCP 도구는 없으므로 기존 core 17 / memory 22개는 유지됩니다.
원칙 내용은 Kev로 보내지 않으며, 로컬 감사 파일에는 내용 대신 버전만 남깁니다.

API: GET/PUT `/api/v1/principles`, POST `/api/v1/principles/resolve`,
GET `/api/v1/principles/history?offset=0&limit=10`. PUT은 전체 목록·`expected_version`·
`approved:true`·`change_note`를 요구합니다. 인증된 owner는 서버가 결정합니다.

## 참고한 가이드와 검증

- [OpenAI Prompt engineering](https://developers.openai.com/api/docs/guides/prompt-engineering): 명확한 지시와 맥락 구분.
- [Anthropic Context engineering](https://www.anthropic.com/research/effective-context-engineering-for-ai-agents): 필요한 컨텍스트를 간결하게 구성.
- [Anthropic Effective harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents): 진행 상태와 결과 검증.

검증은 사용자 격리, CSRF/토큰 경계, 충돌·이력, 마이그레이션, skip·민감 요청에서도 원칙 전달,
실패 시 차단을 포함합니다. 원칙 전달 성공만으로 모델 준수율을 주장하지 않습니다.

Deployment verification (2026-11-03): A10 API and MCP updated; Oracle vk0014 migration succeeded. The approved six-rule bundle was stored via authenticated API at version 1, with one history revision. Live stdio prompt-hook test returned all six rules on Kev skip. 290 tests and ruff/format/mypy passed. The production web editor loaded successfully; browser automation timed out at its confirmation dialog, so a complete browser save interaction is not claimed.
