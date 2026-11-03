# Required memory check before model execution
User request: execute a knowledge MCP check on every submitted prompt; do not rely on the model choosing a tool.
UserPromptSubmit command hook invokes knowledge_decide through the configured stdio MCP. Kev remains the router.
lookup/agent_review trigger knowledge_recall and bounded exact source reads; skip is an explicit completed decision.
Explicit past-memory requests override skip. Sensitive prompts send a fixed placeholder, never original text.
Only current prompt (max 4000 chars) is sent; no transcripts/files/env secrets. Scope is an explicit longest-root mapping;
unmapped workspaces use global only, never infer project identity from folder names.
Retrieved snippets are untrusted data, not developer instructions. Preserve IDs, unavailable/truncation status.
No writes, no profile changes, no automatic memory capture in this hook.
Worker timeout/protocol/provider failures block the prompt. Hard wrapper timeout kills its subprocess group.
No raw error output. Local audit contains status, elapsed time, random check ID and tool names only, not memory bodies.
Installation merges with existing user hooks, backs up settings, supports uninstall; never edits hook trust hashes.
Codex requires /hooks trust. Claude requires restart/reload of settings. CLI/application activation must be independently
verified; successful direct script calls do not prove host execution.
Validation: mock routing/ownership-scope shape, secret handling, failures, timeout, malformed input, config merge,
real read-only MCP hook run and host event tests. macOS/Linux tested first; Windows unsupported for process-group cleanup.

Validation: 283 tests; real MCP read success; Claude event dispatch confirmed but provider expiry prevented model verification; Codex untrusted hook skipped, user trust still required.
