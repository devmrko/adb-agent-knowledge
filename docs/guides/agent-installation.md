# Codex / Claude 공통 스킬 설치

먼저 README대로 서비스와 .env를 구성하고 API/worker를 실행한다.
스킬은 사용 방법이고 MCP는 실제 도구 연결이다. 두 가지를 함께 설정해야 한다.

## Codex
```sh
./.venv/bin/python scripts/install_agent.py codex --register-mcp
```
기본 스킬 위치는 `~/.agents/skills/vector-knowledge`, MCP는 Codex 사용자 설정에 등록한다.
이전 Codex 환경에서 `~/.codex/skills`를 쓰는 경우 `--destination ~/.codex/skills/vector-knowledge`로 지정할 수 있다.
새 세션에서 `$vector-knowledge`로 호출한다.

## Claude Code
```sh
./.venv/bin/python scripts/install_agent.py claude --register-mcp
```
스킬 위치는 `~/.claude/skills/vector-knowledge`. 새 세션에서 `/vector-knowledge`로 호출한다.
이 저장소 안에서만 사용할 경우 `.mcp.json`도 제공한다. 사용자 범위와 프로젝트 범위에
중복 연결하지 않도록 필요한 쪽 하나를 선택한다.

설치 계획만 보기: `--dry-run`. 이미 설치된 스킬 업데이트: `--overwrite`.
`--register-mcp`는 해당 클라이언트의 vector_knowledge 연결을 현재 체크아웃 절대 경로로 등록한다.
Claude에 같은 이름의 연결이 이미 있으면 먼저 기존 설정을 확인해 제거/변경한다.
다른 머신에서는 그 머신의 경로로 설치 명령을 다시 실행한다. 비밀번호는 MCP 설정에 복사하지 않는다.

## 필요한 경우 매 요청 적용
스킬 설치만으로 매 요청 실행이 강제되지는 않는다. 필요하면 Codex의 `~/.codex/AGENTS.md` 또는
Claude의 `~/.claude/CLAUDE.md`에 다음 문장을 기존 지침과 함께 추가한다. 설치 스크립트는
이 파일들을 덮어쓰지 않는다.

> 요청마다 vector-knowledge 스킬을 참고해 지식 조회 필요성을 판단한다.
> Kev의 knowledge_decide로 조회/저장 여부를 판단하되 명시적 지시와 저장 금지를 우선한다.
> 필요한 경우에만 검색하고, 출처 원문을 확인한다.

자동 저장을 원하면 아래 문장을 **사용자 선택으로** 추가한다.

> 확정된 선호·결정·프로젝트 사실·검증된 해결 방법은 별도 요청 없이 선별 저장해도 된다.
> 대화 전체·비밀정보·미검증 추측은 제외하고, 중복을 확인하며 저장 결과를 짧게 알려준다.

## 도구와 확인
knowledge_client_info, knowledge_decide, knowledge_save, knowledge_save_url, knowledge_search, knowledge_list,
knowledge_get_content, knowledge_job_status, knowledge_revise, knowledge_retire,
knowledge_restore, knowledge_history, knowledge_context 외에 인덱스·RDF 탐색 도구를 제공합니다.
전체 도구는 연결한 MCP의 도구 목록으로 확인합니다.

MCP는 Codex/Claude가 실행한다. API·worker는 별도 실행 프로세스다. Kev가 없거나 장애이면
agent_review로 돌아가 에이전트가 판단하며, API가 없으면 실제 저장·조회는 실패한다.

공식 문서: [Codex skills](https://learn.chatgpt.com/docs/build-skills),
[Claude Code skills](https://code.claude.com/docs/en/skills).


## 글로벌/로컬 메모리 중복 방지

개인·프로젝트의 장기 기억은 지식 DB를 기준으로 삼습니다. 글로벌 지침은 조회·저장 정책,
프로젝트 지침은 필수 실행·테스트·보안 규칙과 scope, 로컬 메모리는 짧은 지식/인덱스 참조를 둡니다.
원본 코드·설계·ADR 문서는 근거이므로 그대로 유지합니다. 기존 메모리는 원문 비교와 저장 READY를
확인한 뒤에만 참조로 교체합니다. DB 장애 시 새 Markdown 사본을 만들지 않고 미이전 원문을 보존합니다.

Codex는 `~/.codex/AGENTS.md`, Claude는 `~/.claude/CLAUDE.md`에 이 정책을 넣습니다.
Claude의 별도 자동 로컬 메모리 생성을 끄려면 사용자 선택으로 `~/.claude/settings.json`에
`"autoMemoryEnabled": false`를 설정합니다. MCP를 통한 승인된 선택 저장은 별개로 계속 사용할 수 있습니다.
스킬 설치 스크립트는 사용자 글로벌 지침이나 자동 메모리 설정을 임의로 바꾸지 않습니다.

공식 설정 근거: [Codex 지침](https://learn.chatgpt.com/docs/agent-configuration/agents-md),
[Claude 메모리](https://code.claude.com/docs/en/memory). 적용 후 새 세션에서 확인합니다.

다른 머신에서 파일 검색·정책 미리보기·적용·복원·기존 메모리 이관은 [여러 머신 설정](multi-machine-memory.md)을 따릅니다.

## 로컬·원격 선택과 기존 설치 업데이트

설치 스크립트는 `scripts/run_configured_knowledge_mcp.sh`를 등록한다. 체크아웃의 `.env`
또는 실행 환경에 `KNOWLEDGE_SSH_HOST`가 있으면 SSH MCP를, 없으면 로컬 MCP를 실행한다.
원격 구성은 `KNOWLEDGE_REMOTE_DIR`도 해당 서버의 실제 체크아웃 경로로 지정한다.
스킬 파일만 업데이트하는 `--overwrite`는 기존 MCP 등록을 바꾸지 않는다. 기존 로컬 전용
등록을 전환하려면 연결 설정도 확인하고 `--register-mcp`를 사용한다.

기존 스킬에 머신별 연결 안내를 직접 추가했다면 덮어쓰기 전에 보존한다. 공유 스킬에는
개인의 호스트·경로·키를 넣지 않는다.

### 실행 중 MCP 코드 업데이트 후

Codex CLI 0.165.0에서 `/mcp`는 상태 목록이며 재연결 메뉴가 아니다. `/quit` 후 터미널에서
`codex resume --last`로 재개한다. Claude Code에서는 `/mcp`에서 서버를 선택하고 Reconnect한다.
`connected` 표시만으로 새 코드 적용을 확인할 수는 없다. `knowledge_search`를
`graph_mode=always`로 호출해 `graph.paths`, `graph.related_knowledge`, `graph.retrieval_lanes`가
반환되는지 확인한다. 빈 배열은 관계가 없는 정상 결과일 수도 있다.
