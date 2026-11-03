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
so Claude model consumption was not verified. Codex initially returned HOOK_MISSING while untrusted.
Subsequent real user prompts in this installation delivered Memory check completed before the answer:
both a Kev skip and a lookup with exact source revision excerpts were observed. Other installations still
require their own trust and end-to-end checks.


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
Claude dispatch/MCP reads were observed; model consumption after the expiry error remains unverified.

## Troubleshooting and other machines

- MCP connected is not hook activation. Install the hook on the agent client machine.
- Codex: review the exact memory_prompt_hook.py UserPromptSubmit command in /hooks. Start a new session
  if the app has not loaded the new configuration.
- Claude: a COMPLETE hook audit and a client expiry/authentication error are separate. Resolve the
  client error using its login guidance, then verify a fresh prompt.
- skip means the mandatory MCP routing call completed; additional retrieval was skipped.
- COMPLETE does not guarantee relevant retrieval. Exclude irrelevant matches; check explicit scope mappings.
- Brief follow-ups such as “Claude too?” lack standalone context. The hook does not read the transcript;
  the agent must interpret the live conversation and perform additional focused retrieval when necessary.
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
