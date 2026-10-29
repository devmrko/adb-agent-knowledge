# 머신 및 출처 위치

각 revision에 origin_machine_id/label과 sources JSON snapshot을 저장한다. 머신 ID는 클라이언트가
명시하는 안정적인 ID이며 인증 수단이 아니다. API 서버의 hostname을 출처 머신으로 추정하지 않는다.
새 설치는 랜덤 UUID를 .env에 생성한다. 기존 .env는 보존하며 명시적 설정으로 추가한다.
MCP는 자신의 .env에서 머신 ID를 읽어 저장/수정 요청에 첨부한다. 여러 머신에서 하나의 API를
쓰더라도 MCP가 실행되는 클라이언트별 설정이 다르다. .env를 머신 간 복사하면 ID도 복제되므로
새 머신에서는 새 ID를 설정해야 한다. hostname/MAC 주소/IP를 자동 수집하지 않는다.

sources는 kind(local_file/url/git/object/reference), location, machine_id, version, locator이다.
로컬 파일은 출처 머신 ID가 필수. location은 읽거나 업로드하지 않는 참조이며 절대 경로/URI/객체 ID
등을 저장한다. URL 자격증명/쿼리는 거부해 비밀 포함 링크를 예방한다. scope/소유자 권한은 유지한다.
기존 문서에는 null/빈 출처를 반환하며 과거 머신/위치를 추정해 채우지 않는다.
수정은 활성 revision의 출처에 새 출처를 중복 없이 누적한다(최대100). 실패한 미활성 revision의
출처는 자동 상속하지 않는다. 동일 지식 내용의 병합은 에이전트 책임이고 자동 파일 동기화는 아니다.

API JSON 저장/수정, multipart 업로드, MCP 저장/URL/수정 모두 지원한다. 원문/이력에서 출처를 반환하며
검색 화면 원문 창에 표시한다. Oracle additive migration vk0003, 재임베딩 불필요.
