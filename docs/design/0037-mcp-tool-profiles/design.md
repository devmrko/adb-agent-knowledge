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
