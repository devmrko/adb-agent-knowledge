# Agent Memory JSON storage feasibility

Experiment only. No production migration or contract change.
Use an existing VKV_/OAM_TEST_ validation account and a new isolated SDK store.
Synthetic Korean JSON only; retain test data, never recreate or drop existing stores.
Test content as serialized JSON, native metadata with nested fields/arrays, separate index_texts,
metadata filtering, replacement semantics and content/index changes, size round trips.
Use a deterministic probe embedder to inspect the SDK indexing pipeline without model cost.
This verifies storage and indexing plumbing, NOT semantic relevance, model token limits or throughput.
Report measured lower bounds separately from Oracle JSON type capacity and application DTO limits.
Do not infer revision preservation, RDF/evidence compatibility or successful migration from JSON round trips.
