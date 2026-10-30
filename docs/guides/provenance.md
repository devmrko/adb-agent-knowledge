# 머신과 원문 위치

원문/이력 응답에는 `origin_machine_id`, `origin_machine_label`, `sources`가 포함된다.
작성 머신은 수정한 클라이언트이고 sources의 machine_id는 실제 파일이 있는 머신이다.
서로 다를 수 있다. 이 값은 사용자가 선언하는 출처 정보이며 인증/접근 권한이 아니다.

새 setup은 `.env`에 랜덤 KNOWLEDGE_MACHINE_ID를 생성한다. 기존 설치는 다음 값을 추가한다.
각 머신에서 다른 ID를 사용하고 프로젝트 이동/재시작 때에는 같은 값을 유지한다.
동일 머신의 여러 checkout에서 동일 ID를 쓰려면 명시적으로 같은 값을 설정한다.

```dotenv
KNOWLEDGE_MACHINE_ID=my-dev-mac
KNOWLEDGE_MACHINE_LABEL=개발 Mac
```

MCP는 클라이언트 설정을 저장/수정 요청에 자동 첨부한다. API 직접 호출자는 필드를 직접 보낸다.
`knowledge_client_info`로 ID/라벨을 확인할 수 있다. API 서버 ID로 대신 기록하지 않는다.

저장 또는 수정 JSON에 다음 필드를 추가한다:

```json
{
  "origin_machine_id": "my-dev-mac",
  "origin_machine_label": "개발 Mac",
  "sources": [
    {"kind":"local_file","location":"/work/project/docs/design.md","machine_id":"my-dev-mac","version":"git-commit-sha","locator":"lines 10-30"},
    {"kind":"object","location":"object://knowledge/spec-001","version":"v2"}
  ]
}
```

kind는 local_file/url/git/object/reference. local_file은 machine_id가 필수이며 위치는 자동으로
읽거나 동기화하지 않는다. URI에 로그인 정보나 query string을 넣을 수 없다. 커밋/페이지/구간은
version/locator로 기록한다. multipart 파일 업로드는 위 객체를 JSON 문자열 `provenance` 폼 필드로 보낸다.

출처는 현재 활성 revision에서 상속하고 새 출처를 중복 없이 추가한다(최대 100개).
이전 버전은 변경하지 않는다. 과거 자료에 머신이나 경로가 없으면 기록 없음으로 표시한다.
검색 화면의 원문 보기에서 작성 머신과 모든 누적 출처를 확인할 수 있다.

출처 컬럼은 vk0003에서 도입됐다. 기존 DB는 API/worker를 중지한 뒤
`./uvw run --extra knowledge --extra mcp alembic upgrade head`로 최신 migration 전체를 적용한다.
현재 head에는 후속 테이블도 포함된다. 출처 컬럼 추가 자체는 기존 벡터 재색인을 요구하지 않는다.
NoSQL/객체 저장소 실제 연동과 원본 위치 자동 이동은 아직 제공하지 않는다.
