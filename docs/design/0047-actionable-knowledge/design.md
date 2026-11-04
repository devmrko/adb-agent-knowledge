# Actionable knowledge: proposal, not implemented

Based on the user's supplied onboarding/manufacturing presentation transcript.
The examples are illustrative, not verified company policies or operational data.

## Goal

Answer whether an employee can perform their first task by comparing applicable
requirements with current evidence, then identify the remaining action and owner.
Reuse existing knowledge, identities, source revisions and shared relationships.
Do not introduce a separate ontology product or silently execute business actions.

## Separate three inputs

- Meaning and relationships: employee -> task -> system -> required permission -> approver. Resolve confirmed aliases to stable IDs.
- Current state: source reference, value, observed time, effective time and access rights. A remembered plan is not proof of current assignment or approval.
- Business requirements: approved policy version, applicability, effective period, conditions and authoritative evidence. Existing free-text graph conditions are not executable rules.

The answer contains each condition's satisfied/unsatisfied/unknown result, evidence
versions, evaluation time, unresolved conflicts, next action and confirmed owner.
Missing or stale evidence must not become 'ready'. Relative dates need the original
utterance date/time zone. A source adapter must expose freshness and failure explicitly.

## Roles

Agents propose extracted conditions and explain results. Human business owners approve
policy meaning. Kev selects retrieval paths; it does not establish truth.
SQL/application evaluation compares typed, allowlisted conditions with current state.
Never execute arbitrary LLM-generated rules or SQL. Exact storage for executable
rule versions remains a design decision; do not assume unvalidated JSON is sufficient.

RDF represents shared semantics and policy provenance. A subclass assertion alone
does not propagate arbitrary approval properties. Explicit inference rules and scope
are needed. Oracle inferred graphs require lifecycle/validity management; no claim
that the existing application's RDF integrity checks already provide inference.
Property Graph supports forward/reverse traversal to systems, requests and owners.
Same-database storage does not itself guarantee freshness, snapshot consistency or
identical security. Preserve owner and source permissions across every query.

Reference: https://docs.oracle.com/en/database/oracle/oracle-database/26/rdfrm/sem_apis-create_entailment.html
Oracle recommends CREATE_INFERRED_GRAPH; verify deployed-version support before use.

## Retrieval and change handling

Resolve task and identity, enumerate applicable policy requirements, retrieve current
state, evaluate all required conditions, return evidence and next actions. Top-k
policy retrieval alone cannot establish completeness: use an authoritative policy
index/registry. A changed source or policy invalidates affected current evaluations;
retain their historical inputs/results and re-evaluate. Revoked access, deleted
sources and conflicts yield unknown rather than silently reusing old conclusions.

## Small acceptance scenario

Use isolated fictional A/B/C employees: A and C pending, B approved. Check the
manager's readiness question, security's waiting-users question and the approver's
work queue against the same IDs and policies. Change A to approved and re-evaluate.
Test missing equipment, stale state, conflicting/changed policies, denied access
and retired evidence. Different agents given identical inputs and policy versions
must receive identical condition evaluations. Actual HR connectors and automatic
actions are outside this proposal.
