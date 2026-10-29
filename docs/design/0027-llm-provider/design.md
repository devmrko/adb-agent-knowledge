# Service-side LLM provider interface

2026-10-29. User approved separating generation from graph extraction and documenting where the
model runs: Codex/Claude -> MCP service -> extraction worker -> provider -> validated Oracle writes.

Define a typed CompletionRequest and CompletionProvider.complete(request) -> str contract. Requests
carry model, system/user text, response schema, generation limit and timeout. Providers return complete
JSON text or a safe CompletionError. No provider writes knowledge/graph data or decides publication.
Move HTTP payload/auth/response handling into OpenAICompatibleProvider. Keep extraction prompts,
normalization and independent semantic review in ModelExtractor. AutoGraphService uses ModelExtractor;
HTTPExtractor remains a compatibility class for callers. Support direct provider injection for SDK or
in-process implementations without replacing extraction/review logic.

GRAPH_AUTO_PROVIDER defaults to openai_compatible, preserving existing .env behavior. The packaged
factory supports HTTP now and rejects unsupported names. Local SDK/in-process providers are extension
points, not implemented runtimes; document an explicit factory extension and dependency pinning. Do not
load arbitrary modules from .env or fall back silently to a different provider. Existing provider URL,
remote opt-in, API secret, response size and incomplete-output safeguards stay enforced. Normalize
adapter failures before they can expose raw response bodies; existing worker safe failure handling stays.

Verify transport payloads, structured responses, semantic review through injected provider, malformed/
truncated/oversized/provider failures, remote endpoint policy and current graph lifecycle tests. No
production deployment or claim of live OCI/Gemma execution from mock tests.

The extraction schema endpoint adds provider (the configured provider key) beside model/policy.
Tests validate injected providers independently; real SDK/Gemma execution is not claimed.
