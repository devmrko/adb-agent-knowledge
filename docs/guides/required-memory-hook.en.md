# Required pre-response MCP check

Install a synchronous UserPromptSubmit command hook on the **agent client machine**.
It calls the existing stdio knowledge MCP before the model handles a prompt; it does not merely remind the model.

The hook calls knowledge_decide with principle_scopes to resolve approved user principles and run Kev. Principles are delivered even on skip or sensitive-prompt withholding. Update API/MCP and migrate vk0014 before upgrading this hook. lookup/agent_review triggers recall and up to two exact source reads.
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
Retrieved material is untrusted reference data. Two source excerpts and two agent memories are capped at 1600 characters each.
Exact revision IDs and continuation offsets allow further reads.
Only check ID/time/status/tool names/principle_version are audited at ~/.local/state/adb-agent-knowledge/prompt-hook.jsonl.
No prompt or memory bodies are persisted locally.

The internal deadline defaults to 35 seconds (1–45 configurable), with a 55-second host timeout.
Handled failures emit decision:block; shell startup failures exit 2; Claude additionally uses onFailure:block.
Disabled/untrusted hooks cannot enforce anything; host-level termination remains client-dependent.
macOS/Linux only for this process-group cleanup implementation; Windows is not supported yet.

Add --remove to the same installer command to remove only this hook.
See the [Korean operational guide](required-memory-hook.md) for direct checks and deployment validation.
Official references: [Codex](https://learn.chatgpt.com/docs/hooks), [Claude](https://code.claude.com/docs/en/hooks).

## Validation status (2026-11-03)

290 tests and ruff/format/mypy passed. Oracle vk0014 was applied on A10. Real Codex hook context
injection and a subsequent Claude source-based answer were verified. The live hook returned all six
approved rules at version 1 even on Kev skip. Initial trust, expiry and scope issues were resolved;
other installations still require their own activation checks. This does not establish universal
model compliance or retrieval relevance.

## Why use a hook instead of only registering MCP tools?

A normal MCP tool is optional: the agent may invoke it or omit it based on the request.
This store preserves working context—previous decisions, preferences, progress and failed approaches—
so checking memory must be part of every request, not a tool call the agent can simply forget.

The synchronous UserPromptSubmit hook performs that check before the model responds.
The current implementation always calls knowledge_decide through MCP; Kev then decides whether retrieval
is needed. Mandatory checking does not mean loading every memory or forcing irrelevant facts into the answer.
It also does not mean unconditional vector search on every request: that would be a different policy.
MCP provides storage/retrieval, while the hook establishes when the check must run.

## Claude Code checklist

After installation, open a fresh Claude session and use /hooks to inspect UserPromptSubmit for
memory_prompt_hook.py. Claude's /hooks is a configuration browser, not Codex's hook-trust approval flow.
Ask about a known prior project decision. Check the newest entries with:

```sh
tail -n 3 ~/.local/state/adb-agent-knowledge/prompt-hook.jsonl
```

Compare request time, COMPLETE status and tool names. Ask Claude for the injected check_id and source titles
and compare with the audit; do not rely on its assertion alone. Avoid simultaneous Codex requests during
this check because both clients share this audit file.

For an expiry/login error use claude auth status, then claude auth login for Anthropic account authentication.
For a separately configured API provider, resolve that provider's credentials instead. Restart and retry.
A later Claude run verified model consumption of the injected source; the earlier expiry error is historical.

## Troubleshooting and other machines

- MCP connected is not hook activation. Install the hook on the agent client machine.
- Codex: review the exact memory_prompt_hook.py UserPromptSubmit command in /hooks. Start a new session
  if the app has not loaded the new configuration.
- Claude: a COMPLETE hook audit and a client expiry/authentication error are separate. Resolve the
  client error using its login guidance, then verify a fresh prompt.
- skip means the mandatory MCP routing call completed; additional retrieval was skipped.
- COMPLETE does not guarantee relevant retrieval. Exclude irrelevant matches; check explicit scope mappings.
- Every request uses generic Kev context resolution, not a list of follow-up phrases. Recent dialogue is included only when relevant; uncertain requests return agent_review for focused agent retrieval.
- For another machine, configure that machine's own absolute launcher and confirmed scope_roots,
  install per client, review trust locally, then test both script and real prompt execution.
- After source/path/command updates, rerun the installer as needed and review any renewed Codex trust prompt.
- These are global user hooks and add remote-call latency to every prompt. Hook MCP activity may not appear
  as a model-selected tool bubble; verify the audit and injected check_id instead.

Removal affects only the hook, not stored knowledge. Startup tool profiles and hook activation are independent.

## Explicit related project scopes

A scope_roots value accepts either one project scope string or a nonempty list of up to ten scopes.
Use explicit related scopes when a legacy workspace and a public deployment repository store records separately.
Global is included automatically; the longest matching directory wins. No project identity is inferred or merged,
and read-scope expansion does not change the destination of writes.
Keep the hook's supplied scopes in agent follow-up retrieval.
A real legacy-cwd test previously missed the 22-tool configuration because it excluded the public project scope.
Adding that confirmed scope returned the exact record and source. 284 tests passed.
An outdated local checkout or a top-k miss is not evidence that the record/implementation does not exist.

Follow-up Claude end-to-end verification succeeded on 2026-11-03: with model tool calls disabled and the legacy cwd, Claude answered MCP_TOOL_PROFILE=memory and 22 tools, citing the injected source title and check_id. This supersedes the initial expiry-related pending status above.

## User-approved principles

The hook now requires principle resolution from the server even on Kev skip. Upgrade API/MCP and migrate vk0014 before upgrading this script. No extra MCP tools. See [principles](user-principles.md) / [English](user-principles.en.md).


## Context-aware routing

The hook reads a bounded tail (256 KiB) of the current host-provided transcript, extracting at most two
recent user/final-assistant excerpts (1200 characters). Tools, reasoning and system messages are excluded.
No dialogue cache is written. Standard Codex sessions and Claude projects roots are allowed; configure
`transcript_roots` for custom locations or set `followup_context=false` to disable reading.

`knowledge_decide(resolve_context=true)` scores lookup need, dialogue dependence and standalone query
sufficiency in one Kev call. It returns `retrieval_query` and `context_used`. The query combines selected
input; no generation model rewrites it. `KEV_CONTEXT_MARGIN=0.1` leaves close scores for agent_review.
noul represents the probability of yes; Kev provides checkpoint temperature calibration. Calibration on our own Korean routing distribution has not been established. Topic changes should use the current request alone. The agent
must still reject unrelated results. Old servers retain principle resolution but unresolved queries
are not searched blindly. Update server and client together.

[Codex](https://learn.chatgpt.com/docs/hooks#common-input-fields) documents the transcript format as
unstable. [Claude hook inputs](https://code.claude.com/docs/en/hooks) also supply the session path.
Missing/unsupported data can require agent review. Verify real hook execution after client updates.
Run synthetic evaluation with `python -m scripts.evaluate_context_routing --output .run/context-routing.json`.

### Graph retrieval configuration

The hook defaults to `graph_mode=auto`, retaining Kev graph routing. Set `always` for explicit expansion or `never` to defer graph retrieval to the agent. `graph_expansion=deferred_to_agent` does not mean no relationships exist. The native RDF G_ID query restoration is documented in [validation](../design/0046-v3-recovery/design.md).
