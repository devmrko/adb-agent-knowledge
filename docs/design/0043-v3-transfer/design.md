# Resumable v3 source transfer and routed reads

Add vk_source_transfer per owner/revision: target store/profile, expected content hash, status,
lease token/expiry, attempts, generation, safe error code. QUEUED -> PROCESSING -> VERIFIED -> ACTIVE.
SDK writes are outside the relational transaction. Persist a lease before writing; expired leases
may be reclaimed. Stable SDK keys allow recovery after uncertain writes. Completion requires the
same lease; stale workers cannot activate. Activation is explicit CAS after source/hash/index checks.
Rollback routes reads to verified retained legacy content and records an event; it does not delete SDK data.

Content routing is optional/off by default. Active rows use SDK only and fail closed on missing/corrupt
SDK data (no silent fallback). Inactive/unmigrated rows use legacy content. Graph assertion quote checks
use the same routed body. Existing relational IDs/lifecycle/events and graph tables remain authoritative.
No deletion of original files/body, no production backfill, no v3 release tag. Vector/keyword main search
is NOT switched by enabling source routing; independent SDK search remains the pilot path.

Use owner-scoped service methods for enqueue/activate/rollback; internal workers claim durable rows.
The CLI is a trusted DB-operator interface, not an authenticated public endpoint. It accepts the exact
source issuer/subject. API content reads keep existing authentication and owner checks.
Keep public MCP tool count unchanged. Expose no unauthenticated operator endpoints.
Validate interrupted/uncertain writes, expired lease, stale completion, owner isolation, CAS,
active SDK outage, historical reads without legacy body, rollback preservation and graph quote checks.

Validation: isolated Oracle vk0015 migration, post-write failure/reopen/retry, active SDK reads,
RDF/Property Graph assertions, fail-closed outage + explicit rollback and event preservation passed.
See docs/reference/v3-transfer-validation.json; live multiprocess contention remains unverified.
