# Claude Code에서 지식 저장·검색

## 설치된 연결
저장소 루트 `.mcp.json`에 `vector_knowledge` stdio MCP를 프로젝트 범위로 등록했다.
명령은 상대 경로 `./scripts/run_knowledge_mcp.sh`이며 Claude Code가 저장소 루트에서 시작한다.
토큰은 Codex와 동일하게 프로젝트 `.env`의 KNOWLEDGE_API_TOKEN 또는 DEV_API_TOKEN을 읽고
`.mcp.json`에는 비밀값을 넣지 않는다.

`CLAUDE.md`는 `AGENTS.md`를 import하므로 "Personal knowledge tools" 규칙이 매 세션 적용된다.
프로젝트 MCP 승인은 로컬 `.claude/settings.local.json`의
`enabledMcpjsonServers: ["vector_knowledge"]`로 처리하며 이 파일은 커밋하지 않는다.
다른 체크아웃에서는 첫 세션에서 승인 프롬프트가 뜨거나 같은 설정을 추가한다.

## 사용
도구 이름은 `mcp__vector_knowledge__knowledge_save`, `_save_url`, `_search`, `_list`,
`_get_content`, `_job_status`. 동작 규칙은 [Codex 가이드](codex-knowledge.md)와 같다.
저장은 QUEUED를 반환하므로 READY 확인 전에는 검색 가능하다고 판단하지 않는다.

## 프로세스와 확인
MCP는 Claude Code가 시작하지만 API/worker는 별도로 실행해야 한다.

```sh
./scripts/run_knowledge_api.sh
# 다른 터미널
./scripts/run_knowledge_worker.sh
```

```sh
claude mcp get vector_knowledge   # Scope: Project config, Status: Connected
```

세션 안에서는 `/mcp`로 상태를 확인한다. 연결 해제는 `.mcp.json`에서 항목을 제거한다.

## 검증 — 2026-10-15
- `claude mcp get vector_knowledge`: 프로젝트 범위, stdio 연결 성공.
- 실제 저장/검색 왕복은 새 Claude Code 세션에서 API/worker 실행 후 확인 필요.

공통 관계·프로젝트 연결·시점 조회는 [공통 RDF 가이드](shared-graph.md)를 따른다. 공유 스킬은 knowledge_graph_* 도구를 우선 사용하며 기존 원문별 workflow 도구는 호환용이다.
