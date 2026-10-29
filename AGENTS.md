# Repository development rules

- Root is adb-agent-knowledge (Agent Knowledge for Oracle ADB). Keep Foundation library/example/tests isolated in packages/python-foundation; preserve its distributable wheel contract.
- Write/update docs/design before changing public contracts; document validation and limitations.
- Use Router -> Service -> Repository. Never commit from a repository or share Sessions across tasks.
- Use typed DTOs and safe ErrorSpec/BusinessError. Never expose credentials, SQL or raw provider messages.
- Authentication and CSRF changes require session/token/mixed boundary tests. No implicit token issuance.
- Run uv run ruff check ., uv run ruff format --check ., uv run mypy, uv run pytest.
- Packaging changes also require uv build --package devmrko-python-foundation and uv run python packages/python-foundation/scripts/verify_wheel.py.
- Keep package/application dependencies pinned through uv.lock. Do not commit .env, DBs, keys, virtualenvs or caches.
- Python and Java share HTTP contracts, not source or release cycles. Oracle/live-provider claims require actual tests.
- Keep unfinished capabilities explicit in docs; do not call in-process background work durable.

## Knowledge scope

- For this public repository use `project:adb-agent-knowledge` plus `global`. Existing deployments may retain their confirmed legacy scope; do not rename or migrate stored scopes automatically. Discover indexes by scope/key on each service; do not hardcode another user’s index IDs.
- Detailed memory workflow: `skills/vector-knowledge/SKILL.md`. Connection help: `docs/guides/agent-installation.md`.

<!-- BEGIN vector-knowledge-memory-policy -->
## Durable knowledge references

- Use the installed `vector-knowledge` skill / configured knowledge MCP (default `adb_agent_knowledge`) for personal and project memory. Follow the current user's storage authorization; this file grants none.
- Keep required project/build/test/security instructions here. Store durable decisions, preferences and verified work history in the knowledge DB; local memory should contain short knowledge/index references, not duplicate bodies.
- Reuse the confirmed project scope/index; do not infer that similarly named projects are identical. Read exact content/history before revising an existing fact; confirm READY before replacing a local record with its reference.
- Preserve original source/design/ADR documents as evidence. If the service is unavailable or migration is incomplete, retain existing unique local knowledge and report the gap; do not create a new Markdown memory mirror.
<!-- END vector-knowledge-memory-policy -->
