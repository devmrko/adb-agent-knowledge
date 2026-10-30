# Public preview distribution

> 설계 당시의 결정·계획을 보존한 기록입니다. 현재 기본값·설치·지원 범위는 [현재 매뉴얼](../../README.md)을 기준으로 확인하세요. 이 문서의 계획이나 과거 검증은 현재 구현·배포 보장이 아닙니다.

2026-10-29. Export current application into a separate directory, retaining source, tests,
original design documents and Foundation wheel contract. Do not copy credentials, caches,
user data, personal key-issuance helpers, deployment addresses or the original Git history.
Preserve existing running services and source checkout. Keep current protocol/package identifiers
until a product rename is agreed; changing branding must not invalidate existing MCP or DB identifiers.

Validate locked dependency installation from a new virtual environment, all repository checks,
Foundation build/wheel validation and source secret scanning. Audit original Git history separately.
Do not claim fresh Oracle, RDF privileges, model downloads or live-provider installation based
on SQLite or mock tests. Publish as preview until these independent checks are completed.

Fresh-install verification found the wheel checker required globally installed uv. Default its
existing --uv option to the repository launcher, preserving explicit overrides and avoiding
global tool installation. Re-run wheel validation in a separate environment.

Approved public name: Agent Knowledge for Oracle ADB; repository/package adb-agent-knowledge.
Retain vector_knowledge MCP registration, vector-knowledge skill and DB/API identifiers for compatibility.
