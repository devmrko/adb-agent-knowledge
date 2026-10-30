# Reproducible installation and Oracle validation

2026-10-30: the repository must install its runtime and initialize its own tables/history/triggers.
Validation may provision an isolated database account, but must call the checked-in Alembic/RDF/Property
Graph entrypoints, not recreate application DDL manually. Keep credentials in ignored private files.

Extend setup.sh with --with-models and --verify-models. Use one standard-library Python orchestrator
for OS/prerequisite checks, locked API environment setup, private configuration creation, optional
pinned Kev installation and actual model smoke checks. Preserve existing configuration. Do not install
system GPU drivers or silently change embedding profiles. The local embedding model downloads on smoke
check/first use; Kev downloads on its dedicated startup. Failures must exit nonzero, not report READY.

Supported installer families: macOS and Linux, including WSL's Linux environment. Native Windows is
not supported by the POSIX launchers; fail early with WSL instructions. Intel Mac, Linux CPU/ARM,
AMD/ROCm, WSL and hardware-specific performance remain unverified unless actually tested. Upstream
PyTorch portability is not this application's end-to-end support guarantee. Remote model providers
remain available. Verify models independently and release each process before loading the next.

Oracle integration validation uses an explicitly selected test environment/schema and opt-in flag.
It runs shipped migrations and graph initialization, checks real trigger compilation, source/graph
roundtrip, rollback and isolation. No implicit ADMIN use or existing-schema deletion. Record exact
runtime and validation limits, never credentials. Tests cover installer command routing, no-op plans,
unsupported platforms, subprocess failure, and private config preservation.
