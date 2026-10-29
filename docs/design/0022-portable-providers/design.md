# Portable providers and public onboarding

2026-10-29. User-approved direction: MIT application, Oracle ADB, no mandatory Docker,
Kev as the default decision layer, selectable local/remote inference.

## Contracts

- Keep the existing local embedding profile hash unchanged. Introduce an OpenAI-compatible
  embedding adapter with an explicit immutable model revision, query prefix, bounded character
  chunks and a distinct profile hash. Existing Oracle VECTOR columns remain 1024-dimensional.
- A remote embedding endpoint must be HTTPS or loopback HTTP. Disable redirects and environment
  proxies; never expose provider response bodies or keys in application errors.
- Share a DecisionProvider scoring interface between memory routing and index navigation.
  Kev remains the default. Remote Kev requires explicit opt-in and HTTPS; local HTTP remains valid.
  Failure returns agent_review. Explicit requests and privacy guards keep their precedence.
- Search returns EMBEDDING_PROFILE_MISMATCH (409) for incompatible active vectors within the
  requesting owner and filters, instead of silently returning an empty/partial result.
- A read-only doctor validates configuration and optionally checks DB/vector/profile compatibility.
  It must not print credentials, execute DDL or start/download models implicitly.
- Preserve existing deployment configuration. Public examples must not depend on the maintainer's
  SSH host, home directory or endpoint. Existing remote wrapper defaults require compatibility care.

## Limits

Provider selection is not online model migration. Existing vectors must not be mixed across profiles.
Doctor rejects incompatible stored profiles; use a separate schema for another profile until a
verified reindex/cutover implementation exists. Dimension changes require schema migration.
Remote character chunking is conservative but provider token limits still apply.

## Verification

Mock transports: remote auth, ordering, invalid vectors, provider failures, routing shared interface.
Full ruff/format/mypy/pytest. No claims of fresh ADB, live model quality or model migration without
actual execution. Public release remains gated on secret/history review and fresh-install validation.

## Agent installation follow-through

Register run_configured_knowledge_mcp.sh for both clients so explicit KNOWLEDGE_SSH_HOST
selects the remote adapter and an unset host preserves local behavior. Installing a skill alone
does not change existing MCP registrations. Preserve machine-specific connection instructions
when updating existing personal skills.
