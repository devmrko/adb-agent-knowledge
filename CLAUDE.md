@AGENTS.md

## Claude Code

- 이 저장소의 `.mcp.json`은 기본 이름 `adb_agent_knowledge`로 MCP를 등록한다. 사용자 지정 이름을 선택했다면 실제 등록명을 따른다. 도구 이름은 `mcp__adb_agent_knowledge__knowledge_*` (사용자 지정 등록명에 따라 접두어가 달라질 수 있음).
- 사용자가 개인 지식 저장/검색/조회를 요청하면 항상 이 도구를 사용한다. 웹 검색이나 추측으로 대신하지 않는다.
- 저장 후 QUEUED를 그대로 보고하고, `knowledge_job_status`로 READY를 확인하기 전에는 검색 가능하다고 말하지 않는다.
- 도구가 보이지 않거나 연결 오류가 나면 API/worker 실행 여부를 확인한다: docs/guides/claude-knowledge.md

<!-- BEGIN vector-knowledge-memory-policy -->
## Durable knowledge references

- Use the installed `vector-knowledge` skill / configured knowledge MCP (default `adb_agent_knowledge`) for personal and project memory. Follow the current user's storage authorization; this file grants none.
- Keep required project/build/test/security instructions here. Store durable decisions, preferences and verified work history in the knowledge DB; local memory should contain short knowledge/index references, not duplicate bodies.
- Reuse the confirmed project scope/index; do not infer that similarly named projects are identical. Read exact content/history before revising an existing fact; confirm READY before replacing a local record with its reference.
- Preserve original source/design/ADR documents as evidence. If the service is unavailable or migration is incomplete, retain existing unique local knowledge and report the gap; do not create a new Markdown memory mirror.
<!-- END vector-knowledge-memory-policy -->
