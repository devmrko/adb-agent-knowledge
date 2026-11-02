# MCP tool profiles
Default stdio startup exposes core (16 tools); full preserves all tools.
No generic execute dispatcher or hidden-call bypass. Removed tools are uncallable on core.
Core retains Kev, unified recall, exact content/history, bounded listing, prepare/save/revise/job status,
client provenance and SDK search/save/title correction/evidence/graph reads.
Graph/index/profile authoring, imports and operations require full. Guidance explicitly reports
deferred follow-up; core does not claim graph completion. No data, HTTP auth or SDK semantics change.
MCP_TOOL_PROFILE env overrides checkout .env; default core; invalid values fail startup.
Changing profile requires reconnect; do not connect both profiles by default.
Validation: catalog counts, removed-tool rejection without HTTP request, existing full contracts,
full required project checks and live initialize catalog.

## In-session tool selection
Add knowledge_tools(profile) to every profile: core becomes 17, full 64.
It replaces optional tools with one task-specific set (memory, graph, organize, operations)
rather than accumulating all prior tools. Core remains present. No data writes or permission grant.
Use MCP tools/list_changed and advertise listChanged=true on stdio. One process serves one client;
this is not a shared HTTP server/session selector. Clients must refresh tool discovery; if they do not,
use a static startup profile and reconnect. Do not claim Codex/Claude refresh support without observing it.
Preserve annotations/schemas on re-registration. Switching back to core removes advanced callability.
Tests cover switch/restore, notification, repeated requests, invalid profiles and real stdio handshake.

Validation outcome: 278 tests passed; ruff/format/mypy passed. Real stdio initialization advertised listChanged; six task-profile switches sent six notifications and exposed expected tool counts. Codex/Claude UI refresh remains client-dependent and unverified.
