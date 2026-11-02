"""Owner-scoped SDK memory, profile naming and bounded browsing."""

import hashlib
import json
import threading
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Column, MetaData, String, Table, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from knowledge_app.agent_memory_contracts import MemoryQuery, MemoryRename, MemorySave, ProfileSave
from knowledge_app.agent_memory_repository import SDKRepository
from knowledge_app.service import fail, owner_id
from python_foundation.errors import BusinessError, ErrorCategory
from python_foundation.security import Actor

locks = Table("vk_memory_lock", MetaData(), Column("owner_id", String(64), primary_key=True))
TYPES = ("memory", "fact", "preference", "guideline")
PROFILE_TYPES = {"user": "user_profile", "agent": "agent_profile", "thread": "thread"}


def stable_id(owner: str, kind: str, key: str) -> str:
    return hashlib.sha256(json.dumps([owner, kind, key]).encode()).hexdigest()


class AgentMemoryService:
    def __init__(self, repository: SDKRepository, engine: Engine, enabled: bool) -> None:
        self.repo, self.engine, self.enabled = repository, engine, enabled
        self._write_lock = threading.RLock()

    def check(self) -> None:
        if not self.enabled:
            raise fail("AGENT_MEMORY_NOT_CONFIGURED", ErrorCategory.UNAVAILABLE)

    def profile_record(self, owner: str, kind: str, record_id: str) -> Any:
        row = self.repo.store.get(PROFILE_TYPES[kind], record_id)
        if row is None or (row.metadata or {}).get("owner_id") != owner:
            raise fail("MEMORY_PROFILE_NOT_FOUND", ErrorCategory.NOT_FOUND)
        return row

    def profile_view(self, row: Any, kind: str) -> dict[str, Any]:
        m = row.metadata or {}
        return dict(
            id=row.id,
            kind=kind,
            name=m.get("display_name", row.id[:8]),
            description=m.get("description", ""),
            version=m.get("name_version", 1),
            scope=m.get("scope", "global"),
            agent_id=getattr(row, "agent_id", None),
        )

    def profiles(self, actor: Actor) -> dict[str, Any]:
        if not self.enabled:
            return {"status": "NOT_CONFIGURED", "items": []}
        try:
            owner = owner_id(actor)
            items: list[dict[str, Any]] = []
            for kind, record_type in PROFILE_TYPES.items():
                rows = self.repo.store.list(record_type, metadata_filter={"owner_id": owner}, limit=201)
                items.extend(self.profile_view(r, kind) for r in rows[:200])
            return {"status": "READY", "items": items, "limit_per_kind": 200}
        except BusinessError:
            raise
        except Exception:
            raise fail("AGENT_MEMORY_UNAVAILABLE", ErrorCategory.UNAVAILABLE) from None

    def mutate(self, owner: str, operation: Any) -> dict[str, Any]:
        # Cross-process DB row lock; SDK transactions are independent and remain idempotent.
        with self._write_lock:
            try:
                with self.engine.begin() as con:
                    if con.execute(select(locks.c.owner_id).where(locks.c.owner_id == owner)).first() is None:
                        con.execute(locks.insert().values(owner_id=owner))
            except IntegrityError:
                pass
            with self.engine.begin() as con:
                con.execute(
                    select(locks.c.owner_id).where(locks.c.owner_id == owner).with_for_update()
                ).first()
                result: dict[str, Any] = operation()
                return result

    def save_profile(self, command: ProfileSave, actor: Actor) -> dict[str, Any]:
        self.check()
        owner = owner_id(actor)
        record_id = owner if command.kind == "user" else stable_id(owner, command.kind, command.key)

        def write() -> dict[str, Any]:
            typ = PROFILE_TYPES[command.kind]
            row = self.repo.store.get(typ, record_id)
            previous = dict(row.metadata or {}) if row is not None else {}
            if row is not None and previous.get("owner_id") != owner:
                raise fail("MEMORY_PROFILE_NOT_FOUND", ErrorCategory.NOT_FOUND)
            version = previous.get("name_version", 0)
            if command.expected_version != version:
                raise fail("MEMORY_PROFILE_VERSION_CONFLICT", ErrorCategory.CONFLICT)
            if command.agent_id:
                self.profile_record(owner, "agent", command.agent_id)
            if (
                row is not None
                and command.kind == "thread"
                and command.agent_id != getattr(row, "agent_id", None)
            ):
                raise fail("MEMORY_THREAD_AGENT_IMMUTABLE")
            metadata = {
                **previous,
                "owner_id": owner,
                "display_name": command.name,
                "description": command.description,
                "scope": command.scope,
                "name_version": version + 1,
                "schema_version": 1,
                "name_origin": "user",
                "name_updated_at": datetime.now(UTC).isoformat(),
            }
            if row is not None:
                self.repo.store.update(typ, record_id, metadata=metadata)
            elif command.kind == "user":
                self.repo.client.add_user(record_id, command.description, metadata=metadata)
            elif command.kind == "agent":
                self.repo.client.add_agent(record_id, command.description, metadata=metadata)
            else:
                kwargs = {"agent_id": command.agent_id} if command.agent_id else {}
                self.repo.client.create_thread(
                    thread_id=record_id,
                    user_id=owner,
                    metadata=metadata,
                    enable_context_summary=False,
                    **kwargs,
                )
            return self.profile_view(self.repo.store.get(typ, record_id), command.kind)

        try:
            return self.mutate(owner, write)
        except BusinessError:
            raise
        except Exception:
            raise fail("AGENT_MEMORY_WRITE_UNCERTAIN", ErrorCategory.UNAVAILABLE) from None

    def save(self, command: MemorySave, actor: Actor) -> dict[str, Any]:
        self.check()
        owner = owner_id(actor)
        record_id = stable_id(owner, "memory", command.idempotency_key)
        digest = hashlib.sha256(command.model_dump_json().encode()).hexdigest()

        def write() -> dict[str, Any]:
            for typ in TYPES:
                existing = self.repo.store.get(typ, record_id)
                if existing is not None:
                    if existing.user_id != owner or (existing.metadata or {}).get("request_digest") != digest:
                        raise fail("MEMORY_IDEMPOTENCY_CONFLICT", ErrorCategory.CONFLICT)
                    return {"memory_id": record_id, "status": "READY", "reused": True}
            if command.agent_id:
                self.profile_record(owner, "agent", command.agent_id)
            if command.origin_thread_id:
                thread = self.profile_record(owner, "thread", command.origin_thread_id)
                if command.agent_id and thread.agent_id != command.agent_id:
                    raise fail("MEMORY_THREAD_AGENT_MISMATCH")
            metadata = {
                "title": command.title,
                "scope": command.scope,
                "owner_id": owner,
                "origin_thread_id": command.origin_thread_id,
                "request_digest": digest,
                "schema_version": 1,
            }
            kwargs = {"agent_id": command.agent_id} if command.agent_id else {}
            self.repo.client.add_memory(
                command.text,
                memory_type=command.memory_type,
                memory_id=record_id,
                user_id=owner,
                metadata=metadata,
                autonomous_linking=False,
                **kwargs,
            )
            return {"memory_id": record_id, "status": "READY", "reused": False}

        try:
            return self.mutate(owner, write)
        except BusinessError:
            raise
        except Exception:
            raise fail("AGENT_MEMORY_WRITE_UNCERTAIN", ErrorCategory.UNAVAILABLE) from None

    def rename(self, command: MemoryRename, actor: Actor) -> dict[str, Any]:
        self.check()
        owner = owner_id(actor)

        def write() -> dict[str, Any]:
            for typ in TYPES:
                row = self.repo.store.get(typ, command.memory_id)
                if row is None:
                    continue
                metadata = dict(row.metadata or {})
                if row.user_id != owner or metadata.get("owner_id") != owner:
                    raise fail("MEMORY_NOT_FOUND", ErrorCategory.NOT_FOUND)
                current = metadata.get("title", "")
                if current == command.title:
                    return {"memory_id": row.id, "title": current, "unchanged": True}
                if current != command.expected_title:
                    raise fail("MEMORY_TITLE_CONFLICT", ErrorCategory.CONFLICT)
                history = list(metadata.get("title_history", []))[-19:]
                history.append(
                    {"title": current, "changed_at": datetime.now(UTC).isoformat(), "reason": command.reason}
                )
                metadata.update(title=command.title, title_history=history)
                self.repo.store.update(typ, row.id, metadata=metadata)
                return {"memory_id": row.id, "title": command.title, "unchanged": False}
            raise fail("MEMORY_NOT_FOUND", ErrorCategory.NOT_FOUND)

        try:
            return self.mutate(owner, write)
        except BusinessError:
            raise
        except Exception:
            raise fail("AGENT_MEMORY_WRITE_UNCERTAIN", ErrorCategory.UNAVAILABLE) from None

    def query(self, command: MemoryQuery, actor: Actor) -> dict[str, Any]:
        if not self.enabled:
            return {"status": "NOT_CONFIGURED", "items": [], "next_offset": None}
        owner = owner_id(actor)
        try:
            filters: dict[str, Any] = {"user_id": owner}
            metadata: dict[str, Any] = {}
            if command.agent_id:
                self.profile_record(owner, "agent", command.agent_id)
                filters["agent_id"] = command.agent_id
            if command.thread_id:
                self.profile_record(owner, "thread", command.thread_id)
                metadata["origin_thread_id"] = command.thread_id
            if command.scope:
                metadata["scope"] = command.scope
            if metadata:
                filters["metadata_filter"] = metadata
            cap = 1000
            typed: list[tuple[str, Any]] = []
            if command.query:
                results = self.repo.client.search(
                    command.query,
                    **filters,
                    max_results=100,
                    record_types=list(TYPES),
                    include_invalid_results=command.include_invalid,
                    num_hops=0,
                )
                typed = [(str(getattr(r.record, "record_type", "memory")), r.record) for r in results]
                cap = 100
            else:
                for typ in TYPES:
                    typed.extend((typ, r) for r in self.repo.store.list(typ, **filters, limit=cap + 1))
                typed.sort(key=lambda pair: (str(pair[1].timestamp or ""), pair[1].id), reverse=True)
            typed = [
                (typ, r)
                for typ, r in typed
                if r.user_id == owner
                and (command.include_invalid or str(getattr(r.status, "value", r.status)).lower() == "valid")
            ]
            truncated = len(typed) >= cap
            typed = typed[:cap]
            labels = {p["id"]: p["name"] for p in self.profiles(actor)["items"]}
            items: list[dict[str, Any]] = []
            for typ, r in typed[command.offset : command.offset + command.limit]:
                m = r.metadata or {}
                items.append(
                    dict(
                        memory_id=r.id,
                        result_kind="agent_memory",
                        memory_type=typ,
                        title=m.get("title") or (r.content or "")[:120],
                        text=r.content or "",
                        status=str(getattr(r.status, "value", r.status)),
                        scope=m.get("scope", "global"),
                        agent_id=r.agent_id,
                        agent_name=labels.get(r.agent_id, r.agent_id),
                        thread_id=m.get("origin_thread_id"),
                        thread_name=labels.get(m.get("origin_thread_id")),
                        timestamp=r.timestamp,
                    )
                )
            end = command.offset + command.limit
            return dict(
                status="READY",
                items=items,
                next_offset=end if end < len(typed) else None,
                truncated=truncated,
                retrieval_limit=cap,
            )
        except BusinessError:
            raise
        except Exception:
            raise fail("AGENT_MEMORY_UNAVAILABLE", ErrorCategory.UNAVAILABLE) from None
