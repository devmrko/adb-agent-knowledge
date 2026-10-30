# Portable repository and agent skill

> 설계 당시의 결정·계획을 보존한 기록입니다. 현재 기본값·설치·지원 범위는 [현재 매뉴얼](../../README.md)을 기준으로 확인하세요. 이 문서의 계획이나 과거 검증은 현재 구현·배포 보장이 아닙니다.

Clone → scripts/setup.sh → fill .env and unpack Wallet → scripts/run_knowledge.sh --migrate.
Setup installs locked knowledge/MCP dependencies and generates a local API token only for a new .env.
Existing .env is never overwritten. Config paths resolve from the repository; wallet/DSN have no personal defaults.
The foreground supervisor runs API and worker, optionally Kev, forwards shutdown and stops siblings if one exits.
Migration is explicit via --migrate, never silently performed by MCP. API remains loopback by default.
Kev remains optional and separately installed with its own Python 3.13 environment; its model is not downloaded by base setup.
A portable skills/vector-knowledge directory supports Codex and Claude; installation alone does not authorize automatic storage.
An installer copies the skill to a selected target and registers MCP using an absolute checkout path only when explicitly requested.
No .env, Wallet, logs, caches, credentials or local agent settings enter git/distribution archives.
The Foundation wheel stays unchanged; the source archive also includes the runnable knowledge app, migrations and skill.
