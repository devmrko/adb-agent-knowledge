# User-approved principles / 사용자 원칙

## Contract and trust boundary
User principles are explicit owner configuration, not vector hits or SDK memories. A versioned
bundle contains at most 20 rules (6000 instruction characters total), each with stable ID,
title, instruction, global/project scope and enabled flag. Array order is display/application
order. No implicit project override: selected global and project rules are additive; conflicting
rules should be edited by the user. Current user instructions and higher-priority host rules
still take precedence. No guarantee of model compliance or elevation of hook authority.

GET/PUT /api/v1/principles reads/replaces the authenticated owner's bundle, requiring expected
version and explicit approval on writes. GET /api/v1/principles/history is bounded/paginated.
POST /api/v1/principles/resolve returns all enabled rules in explicit scopes plus global.
Every successful replacement creates an immutable application revision in the same transaction.
Atomic compare-and-set prevents lost updates, including concurrent initial creation. Revisions
include the actor, timestamp and change note. No hard-delete endpoint, direct SQL change auditing
or database trigger is claimed. New migration vk0014 creates both tables; no model/index required.

MCP adds an optional principle_scopes argument to knowledge_decide, not another tool. The hook
always requests this configuration before accepting skip, including sensitive prompts (no prompt
text goes to principle resolution). Missing/failed resolution blocks enabled hooks rather than
silently dropping required rules. Deploy API/migration and MCP before upgrading client hooks.
Rules are rendered separately from untrusted retrieved reference data; neither JSON content nor
retrieval can set host/system priority. No automatic translation/LLM rewriting/promotion.

## Web and approval
Existing authenticated browser sessions/CSRF and bearer-token boundaries apply. The rest of the
notes UI stays read-only; only /api/v1/principles PUT is allowed for this editor. Templates are
unpublished drafts until explicit Save and apply. Six requested templates plus three optional
suggestions, never pre-seeded for all users. View effective scopes, preview, enable/disable,
reorder, revisions. Removal is a new bundle revision, not destruction of history.

## Validation
Owner isolation, optimistic concurrency, scope and size validation, history pagination, migration
SQLite/Oracle DDL, browser cookie/CSRF/token boundaries, hook skip/sensitive/failure injection,
MCP routing/provider separation. Full repository checks; live Oracle/deployment only when tested.
