# Alpha documentation and release

2026-11-04. User requests an alpha tag/release and a README that explains purpose,
benefits and technology responsibilities before detailed guides.

Use the GitHub README guidance, Diataxis documentation types and Google developer
style highlights. Root README becomes an entry point: purpose, use cases, outcomes,
component boundaries, a compact workflow, setup with verification, drill-down links,
limits, support and license. Korean and English cover the same contract. Preserve
existing detailed guides; classify routes by reader goals rather than move all files.

Release: v0.3.0-alpha.1 (Python metadata 0.3.0a1). Explicit prerelease; no production
readiness guarantee. Existing installations retain legacy default until v3 is enabled.
No DB schema changes or live service rollout required for this documentation release.

Validation: check referenced source defaults, runnable command flags, local Markdown
paths/anchors, model execution boundaries and bilingual coverage; run existing CI
checks and inspect the pushed commit before tagging. Release notes distinguish
previous live Oracle evidence from checks rerun for this release.

Remaining RDF paths, final auto-mode Claude hook, historical document/memory cleanup
and search evaluation analysis are backlog, not completed by publishing this alpha.
The proposed actionable-knowledge evaluator is outside this release.

Sources:
- https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-readmes
- https://diataxis.fr/start-here/
- https://developers.google.com/style/highlights
