"""Owner-scoped index documents and stable memberships, independent of vector top-k."""

import hashlib
import json
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from knowledge_app import navigation_rdf
from knowledge_app.audit_context import audited_uow
from knowledge_app.contracts import normalize_scope
from knowledge_app.models import IndexChange, IndexEntry, Item, KnowledgeIndex, Revision, now
from knowledge_app.repository import Repository
from knowledge_app.service import fail, item_view, owner_id
from knowledge_app.summaries import summary_view
from python_foundation.database import SqlAlchemyUnitOfWork
from python_foundation.errors import ErrorCategory
from python_foundation.security import Actor


class IndexInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9][a-z0-9._:-]*$")
    scope: str = "global"
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=1000)
    body: str = Field(default="", max_length=20000)
    _scope = field_validator("scope")(normalize_scope)

    @field_validator("title", "summary")
    @classmethod
    def nonblank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Blank index description")
        return v.strip()


class IndexEdit(IndexInput):
    expected_version: int = Field(ge=1)


class EntryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    knowledge_id: UUID
    section: str = Field(default="일반", min_length=1, max_length=120)
    position: int = Field(default=0, ge=0, le=1000000)
    note: str | None = Field(default=None, max_length=300)
    verified: Literal[True]
    expected_version: int | None = Field(default=None, ge=1)

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str | None) -> str | None:
        return value or None


def index_view(index: KnowledgeIndex, body: bool = False) -> dict[str, Any]:
    data = {k: getattr(index, k) for k in ("id", "key", "scope", "title", "summary", "version")}
    data["updated_at"] = index.updated_at.isoformat()
    if body:
        data["body"] = index.body or ""
    return data


class IndexRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, owner: str, index_id: str, lock: bool = False) -> KnowledgeIndex | None:
        stmt = select(KnowledgeIndex).where(KnowledgeIndex.owner_id == owner, KnowledgeIndex.id == index_id)
        return self.session.scalar(stmt.with_for_update() if lock else stmt)

    def catalog(
        self, owner: str, scopes: list[str] | None, query: str, offset: int, limit: int
    ) -> list[KnowledgeIndex]:
        stmt = select(KnowledgeIndex).where(KnowledgeIndex.owner_id == owner)
        if scopes:
            stmt = stmt.where(KnowledgeIndex.scope.in_(set(scopes) | {"global"}))
        if query.strip():
            stmt = stmt.where(
                or_(
                    KnowledgeIndex.title.contains(query, autoescape=True),
                    KnowledgeIndex.summary.contains(query, autoescape=True),
                    KnowledgeIndex.key.contains(query, autoescape=True),
                )
            )
        return list(
            self.session.scalars(
                stmt.order_by(KnowledgeIndex.title, KnowledgeIndex.id).offset(offset).limit(limit)
            )
        )

    def members(
        self, owner: str, index_id: str, scopes: list[str] | None, offset: int, limit: int
    ) -> list[tuple[IndexEntry, Item, Revision]]:
        stmt = (
            select(IndexEntry, Item, Revision)
            .join(Item, (Item.id == IndexEntry.item_id) & (Item.owner_id == IndexEntry.owner_id))
            .join(Revision, (Revision.id == Item.active_revision_id) & (Revision.owner_id == Item.owner_id))
            .where(
                IndexEntry.owner_id == owner,
                IndexEntry.index_id == index_id,
                Item.lifecycle_status == "ACTIVE",
            )
        )
        if scopes:
            stmt = stmt.where(Item.scope.in_(set(scopes) | {"global"}))
        return [
            (e, i, r)
            for e, i, r in self.session.execute(
                stmt.order_by(IndexEntry.section, IndexEntry.position, IndexEntry.id)
                .offset(offset)
                .limit(limit)
            )
        ]

    def unfiled(
        self, owner: str, scopes: list[str] | None, offset: int, limit: int
    ) -> list[tuple[Item, Revision]]:
        stmt = (
            select(Item, Revision)
            .join(Revision, (Revision.id == Item.active_revision_id) & (Revision.owner_id == Item.owner_id))
            .where(
                Item.owner_id == owner,
                Item.lifecycle_status == "ACTIVE",
                ~Item.id.in_(select(IndexEntry.item_id).where(IndexEntry.owner_id == owner)),
            )
        )
        if scopes:
            stmt = stmt.where(Item.scope.in_(set(scopes) | {"global"}))
        return [
            (i, r)
            for i, r in self.session.execute(
                stmt.order_by(Item.created_at, Item.id).offset(offset).limit(limit)
            )
        ]


class IndexService:
    def __init__(self, factory: sessionmaker[Session], rdf_enabled: bool = False):
        self.factory = factory
        self.rdf_enabled = rdf_enabled

    def catalog(
        self, actor: Actor, scopes: list[str] | None = None, query: str = "", offset: int = 0, limit: int = 30
    ) -> dict[str, Any]:
        with SqlAlchemyUnitOfWork(self.factory, read_only=True) as uow:
            rows = IndexRepository(uow.session).catalog(owner_id(actor), scopes, query, offset, limit + 1)
            return {
                "items": [index_view(i) for i in rows[:limit]],
                "next_offset": offset + limit if len(rows) > limit else None,
                "offset": offset,
            }

    def get(self, actor: Actor, index_id: str) -> dict[str, Any]:
        with SqlAlchemyUnitOfWork(self.factory, read_only=True) as uow:
            index = IndexRepository(uow.session).get(owner_id(actor), index_id)
            if not index:
                raise fail("INDEX_NOT_FOUND", ErrorCategory.NOT_FOUND)
            return index_view(index, True)

    def write(self, actor: Actor, command: IndexInput, index_id: str | None = None) -> dict[str, Any]:
        owner = owner_id(actor)
        key = hashlib.sha256(json.dumps([owner, command.scope, command.key]).encode()).hexdigest()
        payload = command.model_dump(exclude={"expected_version"})
        try:
            with audited_uow(self.factory, actor, "INDEXES_WRITE", command) as uow:
                repo = IndexRepository(uow.session)
                index = (
                    repo.get(owner, index_id, True)
                    if index_id
                    else uow.session.scalar(
                        select(KnowledgeIndex).where(KnowledgeIndex.key_hash == key).with_for_update()
                    )
                )
                if index_id:
                    if not index:
                        raise fail("INDEX_NOT_FOUND", ErrorCategory.NOT_FOUND)
                    if not isinstance(command, IndexEdit) or command.expected_version != index.version:
                        raise fail("INDEX_VERSION_CONFLICT", ErrorCategory.CONFLICT)
                    if index.scope != command.scope or index.key != command.key:
                        raise fail("INDEX_IDENTITY_IMMUTABLE", ErrorCategory.CONFLICT)
                elif index:
                    if any((getattr(index, k) or "") != v for k, v in payload.items()):
                        raise fail("INDEX_EXISTS_USE_REVISION", ErrorCategory.CONFLICT)
                    return index_view(index, True)
                if index is None:
                    index = KnowledgeIndex(owner_id=owner, key_hash=key, **payload)
                    uow.session.add(index)
                    uow.session.flush()
                else:
                    for k, v in payload.items():
                        setattr(index, k, v)
                    index.version += 1
                    index.updated_at = now()
                uow.session.add(
                    IndexChange(
                        owner_id=owner,
                        index_id=index.id,
                        version=index.version,
                        payload_json=json.dumps(
                            {"operation": "document", "document": payload}, ensure_ascii=False
                        ),
                    )
                )
                uow.session.flush()
                navigation_rdf.store(
                    uow.session,
                    owner,
                    index.id,
                    [
                        navigation_rdf.edge(
                            navigation_rdf.node("index", index.id),
                            "in_scope",
                            navigation_rdf.node("scope", index.scope),
                        )
                    ],
                    self.rdf_enabled,
                )
                return index_view(index, True)
        except (SQLAlchemyError, ValueError) as error:
            if isinstance(error, IntegrityError):
                raise fail("INDEX_CONCURRENT_UPDATE", ErrorCategory.CONFLICT) from None
            raise fail("INDEX_STORAGE_UNAVAILABLE", ErrorCategory.UNAVAILABLE) from None

    def link(self, actor: Actor, index_id: str, command: EntryInput) -> dict[str, Any]:
        owner = owner_id(actor)
        try:
            with audited_uow(self.factory, actor, "INDEXES_LINK", command) as uow:
                repo = IndexRepository(uow.session)
                index = repo.get(owner, index_id, True)
                if not index:
                    raise fail("INDEX_NOT_FOUND", ErrorCategory.NOT_FOUND)
                item = Repository(uow.session).item(owner, str(command.knowledge_id))
                if not item or (index.scope != "global" and item.scope not in {"global", index.scope}):
                    raise fail("INDEX_MEMBER_NOT_FOUND", ErrorCategory.NOT_FOUND)
                if item.lifecycle_status != "ACTIVE" or not item.active_revision_id:
                    raise fail("INDEX_MEMBER_NOT_READY", ErrorCategory.CONFLICT)
                entry = uow.session.scalar(
                    select(IndexEntry).where(
                        IndexEntry.owner_id == owner,
                        IndexEntry.index_id == index_id,
                        IndexEntry.item_id == item.id,
                    )
                )
                fields = command.model_dump(exclude={"knowledge_id", "verified", "expected_version"})
                if entry and all(getattr(entry, k) == v for k, v in fields.items()):
                    return {"index_id": index_id, "version": index.version, "unchanged": True}
                if entry and command.expected_version != index.version:
                    raise fail("INDEX_VERSION_CONFLICT", ErrorCategory.CONFLICT)
                if command.expected_version is not None and command.expected_version != index.version:
                    raise fail("INDEX_VERSION_CONFLICT", ErrorCategory.CONFLICT)
                if entry:
                    for k, v in fields.items():
                        setattr(entry, k, v)
                else:
                    entry = IndexEntry(owner_id=owner, index_id=index_id, item_id=item.id, **fields)
                    uow.session.add(entry)
                    uow.session.flush()
                assert entry is not None
                revision = Repository(uow.session).revision(owner, item.active_revision_id)
                assert revision is not None
                navigation_rdf.store(
                    uow.session,
                    owner,
                    entry.id,
                    [
                        navigation_rdf.edge(
                            navigation_rdf.node("knowledge", item.id),
                            "member_of",
                            navigation_rdf.node("index", index_id),
                        )
                    ],
                    self.rdf_enabled,
                )
                navigation_rdf.store(
                    uow.session,
                    owner,
                    revision.id,
                    navigation_rdf.revision_rows(revision, item.scope, item.memory_kind),
                    self.rdf_enabled,
                )
                index.version += 1
                index.updated_at = now()
                uow.session.add(
                    IndexChange(
                        owner_id=owner,
                        index_id=index_id,
                        version=index.version,
                        payload_json=json.dumps(
                            {"operation": "member", "knowledge_id": item.id, **fields}, ensure_ascii=False
                        ),
                    )
                )
                return {"index_id": index_id, "version": index.version, "unchanged": False}
        except (SQLAlchemyError, ValueError) as error:
            if isinstance(error, IntegrityError):
                raise fail("INDEX_CONCURRENT_UPDATE", ErrorCategory.CONFLICT) from None
            raise fail("INDEX_STORAGE_UNAVAILABLE", ErrorCategory.UNAVAILABLE) from None

    def entries(
        self,
        actor: Actor,
        index_id: str | None,
        scopes: list[str] | None = None,
        offset: int = 0,
        limit: int = 30,
    ) -> dict[str, Any]:
        owner = owner_id(actor)
        with SqlAlchemyUnitOfWork(self.factory, read_only=True) as uow:
            repo = IndexRepository(uow.session)
            items = []
            if index_id:
                index = repo.get(owner, index_id)
                if not index or (scopes and index.scope not in set(scopes) | {"global"}):
                    raise fail("INDEX_NOT_FOUND", ErrorCategory.NOT_FOUND)
                rows = repo.members(owner, index_id, scopes, offset, limit + 1)
                for e, i, r in rows[:limit]:
                    items.append(
                        {
                            **item_view(i),
                            **summary_view(r),
                            "section": e.section,
                            "position": e.position,
                            "note": e.note,
                            "reference_rdf": navigation_rdf.read(uow.session, owner, e.id),
                        }
                    )
                more = len(rows) > limit
            else:
                unfiled = repo.unfiled(owner, scopes, offset, limit + 1)
                items = [{**item_view(i), **summary_view(r)} for i, r in unfiled[:limit]]
                more = len(unfiled) > limit
            return {"items": items, "offset": offset, "next_offset": offset + limit if more else None}

    def history(self, actor: Actor, index_id: str, offset: int = 0, limit: int = 30) -> dict[str, Any]:
        with SqlAlchemyUnitOfWork(self.factory, read_only=True) as uow:
            owner = owner_id(actor)
            if not IndexRepository(uow.session).get(owner, index_id):
                raise fail("INDEX_NOT_FOUND", ErrorCategory.NOT_FOUND)
            rows = list(
                uow.session.scalars(
                    select(IndexChange)
                    .where(IndexChange.owner_id == owner, IndexChange.index_id == index_id)
                    .order_by(IndexChange.version)
                    .offset(offset)
                    .limit(limit + 1)
                )
            )
            return {
                "changes": [
                    {
                        "version": r.version,
                        "created_at": r.created_at.isoformat(),
                        **json.loads(r.payload_json),
                    }
                    for r in rows[:limit]
                ],
                "next_offset": offset + limit if len(rows) > limit else None,
            }

    def references(
        self, actor: Actor, item_id: str, offset: int = 0, limit: int = 30, revision_id: str | None = None
    ) -> dict[str, Any]:
        with SqlAlchemyUnitOfWork(self.factory, read_only=True) as uow:
            owner = owner_id(actor)
            repo = Repository(uow.session)
            item = repo.item(owner, item_id)
            if not item:
                raise fail("KNOWLEDGE_NOT_FOUND", ErrorCategory.NOT_FOUND)
            revision = repo.revision(owner, revision_id or item.active_revision_id or "")
            if not revision or revision.item_id != item_id:
                raise fail("CONTENT_NOT_READY", ErrorCategory.NOT_FOUND)
            rows = list(
                uow.session.execute(
                    select(KnowledgeIndex, IndexEntry)
                    .join(
                        IndexEntry,
                        (IndexEntry.index_id == KnowledgeIndex.id)
                        & (IndexEntry.owner_id == KnowledgeIndex.owner_id),
                    )
                    .where(IndexEntry.owner_id == owner, IndexEntry.item_id == item_id)
                    .order_by(KnowledgeIndex.title, KnowledgeIndex.id)
                    .offset(offset)
                    .limit(limit + 1)
                )
            )
            return {
                "knowledge_id": item_id,
                "revision_id": revision.id,
                "scope": item.scope,
                "lifecycle_status": item.lifecycle_status,
                "detail_uri": f"/api/v1/knowledge/{item_id}/revisions/{revision.id}/content",
                "original_uri": f"/api/v1/knowledge/{item_id}/revisions/{revision.id}/original",
                "filename": revision.filename,
                "mime_type": revision.mime_type,
                "source_url": revision.source_url,
                "sources": [
                    {**s, "availability": "not_checked"} for s in json.loads(revision.sources_json or "[]")
                ],
                "indexes": [
                    {
                        "index": index_view(i),
                        "section": e.section,
                        "rdf": navigation_rdf.read(uow.session, owner, e.id),
                    }
                    for i, e in rows[:limit]
                ],
                "next_offset": offset + limit if len(rows) > limit else None,
                "rdf": navigation_rdf.read(uow.session, owner, revision.id),
                "graph_query": {"knowledge_id": item_id},
                "index_links_time": "current",
                "source_version_mode": "exact",
            }
