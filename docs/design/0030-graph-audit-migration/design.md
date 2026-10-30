# Graph audit initialization with migrations

2026-10-30 user request: initialize history tables and triggers during migration, including the
previously uncovered graph extraction, proposal, identity and review data.

Add vk0011 after vk0010. Keep applied vk0008/vk0009/vk0010 migrations immutable. Reuse existing
vk_change_event/outbox storage; install five additional row-audit triggers for vk_g_extract,
vk_g_proposal, vk_g_review, vk_g_identity, vk_g_operation. Changes and audit/outbox inserts are
atomic. Existing rows are not backfilled as fabricated historical events. Owner/id are immutable.
Block UPDATE/DELETE on vk_g_operation (append-only service history), as already done for change events.
Audit the operation INSERT; rejected edits do not count as committed history. Never audit audit/outbox
itself, avoiding recursion. Do not call LLMs or networks from triggers. Exclude extraction lease tokens.

New installations run all migrations; existing installations run only vk0011. Oracle DDL commits;
stop writers, require CREATE TRIGGER, check USER_ERRORS before resuming. No destructive downgrade.
The frozen migration generator supports Oracle and SQLite, with distinct names from vk0008.
SQLite metadata-created fixtures also install the extension; production initialization is Alembic.

Graph identity/review API writes attach actor attribution using the existing audited UoW. Service-mode
extraction/proposal writes without a context remain DIRECT_SQL/unattributed, which also covers older
applications and workers; this label must not be described as proof of human SQL execution. Attribution
expansion for nested service-mode transactions is outside this migration's scope.

Validation: new-empty and vk0010-to-head migrations, preservation of existing data, direct SQL
INSERT/UPDATE/DELETE before/after history, rollback and audit failure atomicity, owner isolation,
operation append-only protection, Oracle generated DDL/compile-error handling, full regression suite.
SQLite and generated SQL checks do not claim live Oracle compilation or a production deployment.
