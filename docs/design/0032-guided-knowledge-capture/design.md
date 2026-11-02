# Guided knowledge capture: first vertical slice

## Scope
Keep the current MCP, agent-led extraction, source/revision storage and graph publishing APIs. Add durable clarification to an exact source review. No separate knowledge store or new tables. Domain registry, automated ontology evolution, web question forms and unattended LLM processing are follow-up work, not delivered here.

## Persistence
Reuse vk_g_review as the source-revision aggregate and lock/version boundary. Reuse append-only vk_g_operation snapshots with kind CAPTURE for the latest bounded dialog (up to three questions, source-backed summary and hypotheses). Every change increments the review version and appends a snapshot in the same audited transaction. Existing vk0011 audit triggers cover both tables; no migration needed. This avoids abusing the short review note or storing duplicate source bodies. Latest CAPTURE is selected by owner, review ID and version. Existing REVIEW events remain unchanged.

## Contract
GET /graph/reviews/{item}/capture returns current dialog and source freshness; optional revision_id reads historical dialog. POST creates or replaces a question round, pinned to the current source and expected review version. Replacing questions before completing reconciliation is prohibited. POST /capture/answers records one answer with expected version. Answers allow answered, deferred and not_applicable; deferred remains unresolved. GET exposes pending question IDs and resumes after process/session restart. Writes reject stale or retired sources and cross-owner access. Replayed outdated writes return conflict, so callers reread rather than duplicate.

Questions are natural language, tied to an exact source quote, and include why the ambiguity matters. Hypotheses stay explicitly unverified, outside vector and published graph search. Answers are user assertions submitted by the agent, not independently verified facts or proof of a human interaction. Actor attribution describes the authenticated writer.

## Completion and provenance
Open/deferred questions prevent COMPLETE. Answered questions require an agent to read actual answers and reconcile through existing save/revise/assert tools. Completing a review is still an agent attestation; the server cannot establish semantic correctness. User answers must first be persisted as source knowledge when used as graph evidence: never forge a quote in the original source. Source revision changes retain the old dialog, create the normal new review backlog, and require explicit reconsideration of earlier answers. Dialog writes do not publish relations or mutate original text.

## Workflow
Read exact source and existing objects -> agent submits summary, hypotheses and 1-3 high-impact questions -> client asks user -> submit real answer -> read dialog -> preserve user clarification as source when needed -> existing evidence-backed graph publication -> complete original review. Kev advises optional analysis only, never gates source freshness/ownership checks. Unambiguous knowledge may be published independently of pending clarification. No full conversations or secrets in snapshots.

## Validation
Test source quotes, ownership, optimistic concurrency, unresolved completion, deferred questions, historical access/stale write rejection, persisted resume, history/audit and explicit user-answer evidence publication. Run repository lint/format/types/full tests. SQLite checks do not establish Oracle live behavior; record any live validation separately.

## Implemented validation (2026-11-02)

Public checkout: ruff check, ruff format --check, mypy (63 source files) and full pytest suite passed (266 tests). Added Tasteby current-practice versus mandatory-policy scenario, persisted draft/defer/answer/reconcile flow, real source-backed relation publication, stale/retired source and owner isolation checks, audit history, and MCP payload/auth forwarding. These use SQLite/test providers; no live Oracle run or production deployment was performed for this change. No schema migration was added.


## Web and production rollout
Add a note tab for source-bound clarification. Reuse existing authenticated cookie/CSRF request path; no credential handling changes. Render all model/source/answer text using textContent and textarea values. Protect unsaved answers and navigation races. Old revisions are read-only. Answers never auto-publish into knowledge/graphs. The existing agent reconciles submitted answers later.

Production currently vk0009: code backup plus existing vk0010/vk0011 migrations required. Never deploy credentials or overwrite server configuration. Retain schema additions on code rollback. Publish only the explicitly requested public HR excerpt draft in project:hr-onboarding-demo under the web user's owner. Preserve real test-user answers; pending ownership remains unresolved. Verify HTTPS session, CSRF boundary, Oracle persistence and evidence-backed relationships. Do not claim automatic ontology extraction.


### User correction: MCP writes, read-only web
All data handling goes through MCP. Web displays source, graph, questions and previously recorded answers; no answer entry. Existing note editing and graph mutation controls are hidden/guarded. The request helper permits only GET/HEAD and known read-only POST searches. This is a UI workflow boundary, not a new server authorization role: APIs remain available to MCP and existing authentication is unchanged. The initial HR seed had already been submitted through HTTPS before this correction; do not repeat it. All subsequent handling uses MCP.


## Production outcome — 2026-11-02
Existing vk0010/vk0011 applied from vk0009; API and worker active. Fresh SSH MCP session exposed 53 tools and read the HR source, persistent questions/answers and two relations with oracle_rdf storage and oracle_property_graph candidates. Actual browser verified one HR draft, read-only clarification tab and one deferred ownership question. No new schema migration for capture. Initial HTTPS seeding finished before the MCP-only steering; no duplicate seed. Backup code retained on server in .run/deploy-guided-capture-20261102/before.tar.gz. Private deployment report stays outside version control.

## Semantic relationship gate (agent mode)

Before any graph assert/revise, read the exact source and check this frame:
1. Entities: identify stable business objects and roles; reuse confirmed identities. A document audience is not the eligibility boundary of a business object. Separate the benefit program, enrollment task, applicant role and application conditions.
2. Claim: express one precise subject–predicate–object proposition. A person responsible for meeting an enrollment deadline is not responsible for the entire benefits program. Prefer a specific task object over a vague umbrella object.
3. Applicability: preserve source-stated audience, appointment type, exceptions, preconditions and business time in condition/temporal fields. Do not replace these with a generic demo disclaimer. Read section headings and surrounding sentences, not only a matching quote.
4. Evidence: confirm the quote entails this particular direction, predicate and object. Quote matching, Kev scores and a plausible graph do not establish semantic truth. Preserve all still-valid evidence when revising.
5. Bounds: distinguish facts, hypotheses and unknowns. A new-hire guide does not establish that only new hires receive benefits, nor that all employees are eligible. Missing edges mean unknown, not false. Never fill missing facts with common sense presented as source evidence.
6. Clarify: look up existing knowledge first. If ambiguity changes the meaning, use knowledge_capture_get/draft with at most three source-grounded questions; publish independently clear facts only. Record only actual user answers, preserve answers as source before using them as graph evidence. Silence is not confirmation.
7. Validate: read the stored relation back as a sentence, with its conditions. Check that a reader without the source cannot reasonably infer an unsupported restriction, generalization or responsibility. Correct through history + expected_version_id; mark a review complete only when intended checks are finished and questions resolved.

Example: source tells new hires to meet their own benefits election deadlines.
BAD: New hire → responsible_for → Benefits (ambiguous program ownership).
GOOD: USDA new hire → responsible_for → Meeting own benefits election deadlines.
Condition: advice to new hires; eligibility varies by benefit; does not establish eligibility or exclusion of existing employees. Do not invent an all-employees eligibility edge.

This is agent guidance, not an automatic semantic validator. The server enforces structure, versions and source quotations; the calling agent remains responsible for meaning. Retain unresolved cases instead of forcing a populated graph.
