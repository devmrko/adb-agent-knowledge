# Required pre-response MCP check

Install a synchronous UserPromptSubmit command hook on the **agent client machine**.
It calls the existing stdio knowledge MCP before the model handles a prompt; it does not merely remind the model.

The hook calls knowledge_decide (Kev). lookup/agent_review triggers recall and up to two exact source reads.
Explicit past-context references override skip. Failures block the prompt; skip is a completed routing decision.
No knowledge writes or tool-profile changes occur. Memory use by the model is not guaranteed by retrieval alone.

Copy config/prompt-hook.example.json and set an absolute mcp_command array plus confirmed scope_roots.
Unmapped directories query global only; project identities are never inferred from folder names.
Use the existing authenticated launcher; do not add credentials to the hook config.

```sh
./.venv/bin/python scripts/install_memory_hook.py codex --config /absolute/path/prompt-hook.json
./.venv/bin/python scripts/install_memory_hook.py claude --config /absolute/path/prompt-hook.json
```

Existing hooks are preserved and settings are backed up. Installation is idempotent.
**Codex requires reviewing/trusting the new command in /hooks.** The installer never changes trust hashes
or bypasses review. Restart/reload the client and verify a real prompt, not only a direct script invocation.
Claude onFailure:block requires 2.1.295+. Initial checks used Codex 0.165.0 and Claude 2.1.303.

The current prompt is capped at 4000 characters. Transcripts and referenced files are not read.
Obvious secret patterns replace the whole query with a fixed sensitive placeholder; this is not comprehensive DLP.
Retrieved material is untrusted reference data. Two source excerpts and two SDK memories are capped at 1600 characters each.
Exact revision IDs and continuation offsets allow further reads.
Only check ID/time/status/tool names are audited at ~/.local/state/adb-agent-knowledge/prompt-hook.jsonl.
No prompt or memory bodies are persisted locally.

The internal deadline defaults to 35 seconds (1–45 configurable), with a 55-second host timeout.
Handled failures emit decision:block; shell startup failures exit 2; Claude additionally uses onFailure:block.
Disabled/untrusted hooks cannot enforce anything; host-level termination remains client-dependent.
macOS/Linux only for this process-group cleanup implementation; Windows is not supported yet.

Add --remove to the same installer command to remove only this hook.
See the [Korean operational guide](required-memory-hook.md) for direct checks and deployment validation.
Official references: [Codex](https://learn.chatgpt.com/docs/hooks), [Claude](https://code.claude.com/docs/en/hooks).

## Validation status (2026-11-03)

283 tests passed. A direct real-MCP hook invocation returned exact memory sources in about 4.3 seconds.
Claude Code dispatched the hook and completed four read calls, but the client returned an expiry error,
so model consumption was not verified. Codex returned HOOK_MISSING; the new hook has no trusted hash yet.
User /hooks approval and another actual prompt are required. This is installed, not universally activated.
