# 0036 — SDK memory relationship presentation

User request: retain Oracle SDK semantics while making relationship views understandable.
Presentation only: no relabeling of stored relation types, direction, validity or memory body.
One/few relations show compact source and target cards, full wrapping titles, type/state/date,
a localized relation label, and explicit recorded reason. Raw SDK values remain available.
Supports means supporting information, not proof of truth; valid means currently usable memory.
The full topology is expandable and uses numbered nodes with a full-title legend; no truncation.
Content and exact source evidence can be opened from each card. Web stays read-only.

User also requested comprehensible stored titles. Add memory_rename (title metadata only):
owned memory ID, expected_title compare-and-set, new title; retain previous title/time in
bounded metadata history (last 20 title changes, not full content revision history).
Per-owner DB lock serializes writes. SDK content/vectors/relationships remain untouched.
No inferred replacement of memory facts. Repeated same-target-title request is idempotent.

Validation: owner/version mismatch tests; desktop/mobile full titles and overflow;
expand/collapse topology; raw SDK direction/values; exact evidence links; publish/deploy.
