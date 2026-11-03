# User-approved principles on every request

[한국어](user-principles.md)

Required preferences should not depend on vector similarity or top-k. The authenticated user's
approved configuration is read from Oracle on every enabled prompt-hook invocation, even when Kev
returns skip or the prompt is withheld as sensitive. Principles are kept separate from untrusted
retrieved sources. They do not grant permissions or override higher-priority host instructions or
the current user's explicit request. Injection is not a guarantee of model compliance.

## Manage in the web UI
Open `/knowledge`, sign in, expand **사용자 원칙 · 매 요청에 적용**, and load the current bundle.
Add the six starter drafts or write your own. Optional suggestions are selected individually.
Edit title, instruction, enabled status, order and scope (`global` or `project:<key>`). Preview the
effective instructions for a project, enter a change note, then explicitly approve and apply.
Changes are read on the next supported hook invocation. Nothing is automatically seeded for users.

Starter drafts: respectful Korean, solution-oriented work, proportional planning, simple approaches,
acknowledging/correcting errors, and clear explanations. Optional: distinguish facts from assumptions,
retain task context, verify completion. No automatic LLM rewriting or translation is performed.
Limits: 20 rules, 600 characters per instruction, 6000 total instruction characters. All selected
active rules are included; no top-k truncation. Global and project rules are additive in stored order,
not implicit overrides. Resolve conflicting rules in the editor.

## Storage, security and rollout
Migration `vk0014` creates `vk_principle_bundle` and `vk_principle_revision`. Replacements use an
expected version and preserve full historical bundles, actor identity, timestamp and reason in the
same transaction. Stale updates return 409. Removing a rule preserves history. This feature does not
add triggers for direct SQL edits. Existing knowledge remains read-only in the web; principles alone
are editable. Existing browser session/CSRF and bearer authentication boundaries apply. Shared keys
with the same identity manage the same rules. The approval field records an authenticated assertion,
not cryptographic proof of a human click. There is no MCP principle-writing tool.

Update server code, run `./.venv/bin/alembic upgrade head`, restart API and reconnect old MCP processes,
then update the client hook. See [hook installation](required-memory-hook.en.md). Review/reapprove
modified commands if required by the client. Configure principles in the web and verify injection.
The hook requests `knowledge_decide(principle_scopes=[...])` and requires a READY `user_principles`
response. An outdated server or failed read blocks the request rather than silently dropping rules.
Tool counts remain core 17 / memory 22. Principles are not sent to Kev. Audit logs record
`principle_version`, never the principle bodies. Clients without the hook do not automatically receive them.

Endpoints: GET/PUT `/api/v1/principles`, POST `/api/v1/principles/resolve`, GET
`/api/v1/principles/history?offset=0&limit=10`. PUT requires the complete rules, expected_version,
approved:true and change_note. The server derives ownership from authentication.

Sources informing the recommended templates:
[OpenAI prompting](https://developers.openai.com/api/docs/guides/prompt-engineering),
[Anthropic context engineering](https://www.anthropic.com/research/effective-context-engineering-for-ai-agents),
[Anthropic harness design](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents).
Tests cover isolation, cookie/CSRF/bearer boundaries, version conflicts/history, migrations, skip and
sensitive-prompt delivery, and failure blocking. Delivery tests are not a model-compliance benchmark.

Deployment verification (2026-11-03): A10 API and MCP updated; Oracle vk0014 migration succeeded. The approved six-rule bundle was stored via authenticated API at version 1, with one history revision. Live stdio prompt-hook test returned all six rules on Kev skip. 290 tests and ruff/format/mypy passed. The production web editor loaded successfully; browser automation timed out at its confirmation dialog, so a complete browser save interaction is not claimed.
