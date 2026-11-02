# Oracle AI Agent Memory 26.8 evaluation

Status: experiment; no production backend replacement.

Use the official SDK in a separately locked Python environment. Keep current MCP, Kev,
API, workers and vk_* schema unchanged. Connect only to the existing isolated Oracle
validation account, with an explicit expected-user guard; never initialize as ADMIN.
Use a distinct memory_store_id and synthetic Korean facts, with extraction disabled
and autonomous linking disabled. No private conversations or remote generation LLM.

Verify package import/platform compatibility, current Korean embedder integration,
managed schema creation, scoped vector retrieval, explicit supersedes/contradicts links,
linked retrieval and scope isolation. Preserve historical records and distinguish
invalid direct results from linked historical context. Record real failures and timings.
A sample adapter is experimental, not a production MCP/backend contract. Existing RDF
business entities, temporal evidence and review lifecycle remain outside this spike.

Source: https://docs.oracle.com/en/database/oracle/agent-memory/26.8/guide/api/agentmemory.html
