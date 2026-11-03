# MCP 도구 묶음 선택

## MCP tool profiles

Default core exposes **17 tools**: 16 everyday tools plus knowledge_tools.
Call knowledge_tools(profile="memory" | "graph" | "organize" | "operations") when a follow-up needs more tools.
The selected group replaces the previous optional group; it does not accumulate. After a temporary switch, restore the profile active before the task unless the user chose a new default. Do not assume core: deployments may start in memory (22 tools). Explicitly pass the intended profile to knowledge_tools; its omitted argument defaults to core. The deployment setting and a temporary connection switch are distinct.
- memory: SDK profiles, evidence attachment and memory relationships (22 tools total).
- graph: business relationship preparation, identities, authoring and review (31 total).
- organize: indexes, guided capture and URL import (28 total).
- operations: change reviews, retirement/restoration and service extraction operations (29 total).
- full: every tool, for explicit advanced workflows (64 total).

The server advertises tools.listChanged and sends notifications/tools/list_changed after a change.
This is implemented for one-client-per-process stdio. A client must refresh tools/list to expose new tools
to its model. Protocol behavior is tested; automatic refresh in every Codex/Claude version is not guaranteed.
If refresh does not work, set MCP_TOOL_PROFILE to the desired profile in the server checkout .env and reconnect,
or launch scripts/run_knowledge_mcp.sh --tool-profile graph (replace graph as needed).
SSH clients must configure the remote checkout; local env is not automatically forwarded.

Core recall still returns bounded graph/memory results. Switch to the relevant profile for new relationships
or index memberships; never claim unavailable follow-up work completed. Selective automatic storage permission
still applies; changing the tool catalog neither writes knowledge nor grants permissions.
Do not register all profiles at once. Existing tool names, HTTP endpoints and stored records are unchanged.
