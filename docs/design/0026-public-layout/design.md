# Public naming and repository navigation

> 설계 당시의 결정·계획을 보존한 기록입니다. 현재 기본값·설치·지원 범위는 [현재 매뉴얼](../../README.md)을 기준으로 확인하세요. 이 문서의 계획이나 과거 검증은 현재 구현·배포 보장이 아닙니다.

2026-10-29. User requests a review of public names, folder structure and onboarding clarity.

Use adb-agent-knowledge for the distributable skill directory, frontmatter name, invocation and
new personal installation destination. Keep the MCP default adb_agent_knowledge with --mcp-name.
Existing installed skills/configurations are not migrated automatically. Describe how to avoid
loading old and new skills together. Keep policy management markers and backup paths stable so
existing managed blocks and recovery manifests remain recognizable.

Use adb-agent-knowledge-gemma4:e2b for the example Ollama alias; base model stays unchanged.
Do not rename knowledge_app, database objects or API paths merely to match branding.
Preserve packages/python-foundation and its wheel contract: this is a real workspace dependency.
Keep existing scripts module paths stable and provide task-based navigation. This iteration does
not move source files into src/, split the application, or reorganize internal script imports.

README must distinguish application tables from RDF/Property Graph initialization, and embedding,
Kev and optional extraction LLM preparation. State the canonical relationship tables, RDF evidence,
optional SQL Property Graph traversal, and current verification limits.

Validate skill installation under the new name, existing explicit destinations, config/profile
consistency, doc links, full repo checks, and skill frontmatter. No live DB initialization implied.
