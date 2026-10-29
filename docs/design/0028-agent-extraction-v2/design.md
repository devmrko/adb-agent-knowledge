# v2: agent-led extraction, Kev retained

User approved preserving prior public code as v1 and reducing separate LLM installation/operation
in v2. Tag v1 points to 29fb86c. Main becomes v2 preview (package 0.2.0); no running deployment changed.

GRAPH_EXTRACTION_MODE=agent (default) or service. Agent mode never constructs/calls the generation
provider, discovers/claims automatic jobs, or starts the graph worker in the launcher. Existing
service jobs/proposals remain stored. Enqueue/retry return a safe actionable mode error. Service
mode plus GRAPH_AUTO_ENABLED=true retains the v1 worker/provider path. No automatic fallback to a
service LLM when the agent is unavailable. Local Gemma profile explicitly selects service mode.

Add read-only agent preparation: exact active revision, bounded source preview, schema/patterns,
existing entity candidates and existing-evidence hints. Check ownership, active READY revision,
optional expected revision, and RDF enabled. No extraction-complete record or hidden data mutation.
MCP knowledge_graph_prepare uses Kev graph_extract on bounded context and returns guidance; partial
source decisions never certify absence. Agent reads remaining original pages, resolves entities and
uses existing graph_assert/revise tools. Service validates quotes, owners and current source revision;
semantic responsibility stays with Codex/Claude. No global LLM semantic verifier is required in agent mode.

Revision/source retirement protections and relationship idempotency remain in GraphService. Related
facts from distinct sources are not automatically merged. Existing evidence hints are not proof of
full extraction; no new processing ledger claimed. Selecting one mode prevents automatic dual
processing in one service deployment; separate deployments sharing a DB require consistent config.

Web upload still stores/embeds in agent mode; graphs require an agent request or explicit service
mode. UI explains this instead of implying queued extraction. Kev decide/recall/save/index and
embedding behavior stay intact. Tests: no provider/no graph jobs in agent mode, preparation auth,
stale/retired source, bounded previews, MCP Kev routing, service mode compatibility and full checks.

## Validation

2026-10-29: service-mode compatibility and agent-mode preparation tests cover owner isolation,
stale/retired/pending sources, bounded previews, no generation provider construction or job creation,
existing job preservation/resumption, Kev routing, and partial-source skip escalation to agent review.
No schema migration is required. New Oracle setup and live model quality remain unverified;
existing hosted services are unchanged. No new processing ledger or unattended agent worker is claimed.
