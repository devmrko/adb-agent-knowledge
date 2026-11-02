# MCP 도구 노출 조정

## MCP tool profiles

The default stdio connection now exposes **core: 16 tools** instead of all 63.
Unified recall still returns relevant graph/memory results; HTTP endpoints and stored data are unchanged.
Core supports routine reading, saving and knowledge revision plus SDK memory/title operations.
Graph/index/profile authoring, URL import, retirement and operational reviews require full.
If a response recommends an unavailable tool, report that follow-up as pending, not completed.

Set MCP_TOOL_PROFILE=full in the MCP server checkout .env (or its process environment) and reconnect
for advanced work. For a direct launcher, use scripts/run_knowledge_mcp.sh --tool-profile full.
With SSH, configure the remote checkout; local environment variables are not automatically forwarded.
Do not register both profiles by default: that restores the candidate overload.
Existing tool names and full-profile contracts are preserved. Profiles do not grant permissions.
