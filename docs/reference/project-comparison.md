# Agent memory architecture comparison

> Historical, dated evidence: this record does not certify the current deployment or repeat earlier live tests. See [current documentation](../README.md).

Reviewed 2026-10-29 against official project READMEs. This is an architecture review,
not a controlled performance benchmark. These projects change rapidly.

| Project | Documented emphasis | Implication for Agent Knowledge for Oracle ADB |
|---|---|---|
| [Cognee](https://github.com/topoteretes/cognee/) | Connected memory, graph/vector/code retrieval, automatic routing, small local extraction models, plugins | Local models and routing alone are not unique. Learn from onboarding and connectors. |
| [Graphiti](https://github.com/getzep/graphiti) | Incremental temporal facts, source episodes, semantic/keyword/graph retrieval | Improve entity-first question routing and evidence-bearing paths, not merely graph visualization. |
| [Mem0](https://github.com/mem0ai/mem0) | User/session/agent memory, APIs, entity and temporal retrieval | Learn from SDK ergonomics and evaluation. Current README distinguishes managed benchmark results from open SDK capabilities. |

Our useful combination is Oracle relational data + vectors + RDF and Property Graph projections,
editable notes, exact source revisions, change history, shared cross-machine memory, and Kev decisions.
This is a product fit for Oracle users, not evidence of universal superiority over the above projects.
A single database reduces database-system boundaries, but not the number of inference services or
all consistency problems: asynchronous source indexing and graph extraction still require reconciliation.

## Current weaknesses and next evaluation

- Graph retrieval is mostly bounded expansion from retrieved evidence or explicitly selected entities.
  Entity-seeded search exists, but robust natural-language entity resolution and question-specific
  path planning are incomplete. Kev classifies; it does not prove identity or causal impact.
- Graph storage is richer than its current question-answering utilization. Add tests for project
  dependencies, changes affecting related projects, temporal changes and contradictory evidence.
- LIKE keyword matching is weaker than a tuned full-text/BM25 component.
- Compare full-task latency, missed relevant memories, outdated recommendations after correction,
  repeated failed approaches, token use, and human correction effort. Do not compare only rg speed.
- Measure Kev vs always-search vs agent-decides with the same data and requests. Report unnecessary
  lookups and missed needed lookups separately; thresholds are not calibrated truth probabilities.
- ADB onboarding, embedding profile migration and export/import portability remain release concerns.

Proposed graph work (not implemented by this change): resolve entities independently of document top-k;
choose relation direction/type/time based on question intent; return ranked paths with exact source
revision quotes; bound hops and evidence budget; let users correct false links. A dependency path alone
does not prove runtime outage impact. Validate each type of claim against its evidence.

## Cognee graph retrieval details

Official guides reviewed:
- https://docs.cognee.ai/core-concepts/main-operations/recall
- https://docs.cognee.ai/guides/graph-completion
- https://docs.cognee.ai/guides/hybrid-retrieval-recall
- https://docs.cognee.ai/core-concepts/further-concepts/global-context-index

Graph Completion searches indexed entity names, summaries, chunks and relation labels. It projects
candidate nodes into an in-memory graph fragment, maps vector distances, ranks whole triplets using
endpoint/edge weights (and optional feedback), then returns top triplets. Default ID-filtered projection
keeps edges only when both endpoints were selected; bounded neighborhood projection is also available.
Thus it is not unlimited autonomous multi-hop reasoning and can still miss intermediate nodes.

Hybrid retrieval budgets passages, matched entities with edges, and derived facts separately. Facts
are tied to the entity lane, not an independent fact vector search. only_context skips answer generation.
Our MCP can similarly deliver bounded evidence to the calling agent without a second answer-generating LLM.

The optional Global Context Index adds per-document buckets and a dataset root. Default construction
counts extracted entities/relations instead of calling an LLM; affected texts are embedded. Root plus
matching bucket context helps broader questions but does not replace evidence. This is analogous to
our proposed index orientation, not proof that our current indexes already provide the same behavior.

Current recall auto-routing is three ordered rules with HYBRID_COMPLETION as the common default.
FEELING_LUCKY is a separate LLM selector. Do not describe the default Cognee router as a Kev-like model.
Recommended next increment: independent entity retrieval + relation candidate ranking + explicit
context budgets, then graph-derived index summaries. Keep existing provenance/time/owner checks.
