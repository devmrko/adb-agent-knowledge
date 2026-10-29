# Configurable MCP registration name

2026-10-29. User requests a public default matching adb-agent-knowledge and a selectable MCP name.

Default client registration: adb_agent_knowledge. install_agent.py accepts --mcp-name for both
Codex and Claude. Accept 1–64 ASCII letters/digits/underscore/hyphen, starting with a letter;
reject invalid names before any file write or subprocess. Pass names as argv, never shell text.
The copied skill records the selected registration; shared instructions discover the configured
alias rather than requiring the legacy vector_knowledge prefix. Tool method names knowledge_*,
skill invocation vector-knowledge, API paths, scopes, database contents and server display name
remain independent of the client alias.

Static .mcp.json and config example use the default. --mcp-name configures the user registration
and installed skill, not a shared checkout's project .mcp.json. Document the choice to avoid dual
project/user connections. Existing vector_knowledge registrations are not automatically removed,
renamed or migrated; users may retain the name explicitly with --mcp-name vector_knowledge.

Validation: default/custom/legacy names for both CLIs, exact argv and copied skill consistency,
invalid inputs causing no installation/registration, dry-run causing no changes; full repo checks.
