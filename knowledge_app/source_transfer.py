"""Durable SDK staging and explicit per-revision activation/rollback."""

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from knowledge_app.models import Event, Item, Job, Revision, SourceTransfer
from knowledge_app.repository import Repository
from knowledge_app.service import fail, owner_id, provenance_view
from knowledge_app.source_transfer_repository import TransferRepository
from knowledge_app.summaries import summary_view
from knowledge_app.v3_pilot import SourceEnvelope, VersionedMemoryPilot, digest, record_key, serialized
from python_foundation.database import SqlAlchemyUnitOfWork
from python_foundation.errors import BusinessError, ErrorCategory
from python_foundation.security import Actor


class SourceTransferService:
    def __init__(self, pilot: VersionedMemoryPilot):
        self.pilot, self.factory = pilot, pilot.source.factory
        self.store_id = pilot.sdk.settings.agent_memory_store_id
        self.profile = pilot.source.embedder.profile_id

    def snapshot(self, owner: str, kid: str, rid: str) -> tuple[SourceEnvelope, str]:
        with SqlAlchemyUnitOfWork(self.factory, read_only=True) as uow:
            return self._snapshot(uow.session, owner, kid, rid)

    def _snapshot(self, session: Session, owner: str, kid: str, rid: str) -> tuple[SourceEnvelope, str]:
        repo = Repository(session)
        item, revision = repo.item(owner, kid), repo.revision(owner, rid)
        if item is None or revision is None or revision.item_id != kid:
            raise fail("KNOWLEDGE_NOT_FOUND", ErrorCategory.NOT_FOUND)
        ready = session.scalar(
            select(Job.id).where(Job.owner_id == owner, Job.revision_id == rid, Job.status == "READY")
        )
        if revision.content_text is None or not ready:
            raise fail("CONTENT_NOT_READY", ErrorCategory.CONFLICT)
        data = dict(
            knowledge_id=kid,
            revision_id=rid,
            text=revision.content_text,
            summary=summary_view(revision)["summary"],
            sources=json.loads(revision.sources_json or "[]"),
            source_url=revision.source_url,
            filename=revision.filename,
            **{k: v for k, v in provenance_view(revision).items() if k != "sources"},
        )
        return SourceEnvelope.model_validate(data), item.scope

    def enqueue(self, actor: Actor, kid: str, rid: str) -> dict[str, Any]:
        owner = owner_id(actor)
        envelope, _ = self.snapshot(owner, kid, rid)
        checksum = digest(serialized(envelope))
        try:
            with SqlAlchemyUnitOfWork(self.factory) as uow:
                repo = TransferRepository(uow.session)
                row = repo.get(owner, rid)
                if row is None:
                    row = SourceTransfer(
                        owner_id=owner,
                        revision_id=rid,
                        knowledge_id=kid,
                        store_id=self.store_id,
                        profile_id=self.profile,
                        content_digest=checksum,
                        status="QUEUED",
                        generation=1,
                        attempts=0,
                    )
                    uow.session.add(row)
                    uow.session.flush()
                elif (row.knowledge_id, row.store_id, row.profile_id, row.content_digest) != (
                    kid,
                    self.store_id,
                    self.profile,
                    checksum,
                ):
                    raise fail("V3_TRANSFER_CONFLICT", ErrorCategory.CONFLICT)
                return self.view(row)
        except IntegrityError:
            raise fail("V3_TRANSFER_RETRY", ErrorCategory.CONFLICT) from None

    @staticmethod
    def view(row: SourceTransfer) -> dict[str, Any]:
        return dict(
            knowledge_id=row.knowledge_id,
            revision_id=row.revision_id,
            status=row.status,
            generation=row.generation,
            attempts=row.attempts,
            error_code=row.error_code,
        )

    def status(self, actor: Actor, rid: str) -> dict[str, Any]:
        with SqlAlchemyUnitOfWork(self.factory, read_only=True) as uow:
            row = TransferRepository(uow.session).get(owner_id(actor), rid)
            if row is None:
                raise fail("V3_TRANSFER_NOT_FOUND", ErrorCategory.NOT_FOUND)
            return self.view(row)

    def validate_sdk(self, owner: str, kid: str, rid: str, checksum: str) -> SourceEnvelope:
        envelope = self.pilot.read_owned(owner, kid, rid)
        if digest(serialized(envelope)) != checksum:
            raise fail("V3_TRANSFER_INTEGRITY", ErrorCategory.CONFLICT)
        chunks = [p.text for p in self.pilot.source.embedder.split(envelope.text)]
        try:
            valid = self.pilot.sdk.verify_source_index(record_key(owner, kid, rid), owner, chunks)
        except Exception:
            raise fail("V3_INDEX_UNAVAILABLE", ErrorCategory.UNAVAILABLE) from None
        if not valid:
            raise fail("V3_INDEX_INTEGRITY", ErrorCategory.CONFLICT)
        return envelope

    def process_one(self) -> bool:
        with SqlAlchemyUnitOfWork(self.factory) as uow:
            claimed = TransferRepository(uow.session).claim(self.store_id, self.profile)
        if claimed is None:
            return False
        owner, rid, token = claimed
        try:
            with SqlAlchemyUnitOfWork(self.factory, read_only=True) as uow:
                row = TransferRepository(uow.session).get(owner, rid)
                assert row is not None
                kid, checksum = row.knowledge_id, row.content_digest
            envelope, scope = self.snapshot(owner, kid, rid)
            if digest(serialized(envelope)) != checksum:
                raise fail("V3_TRANSFER_SOURCE_CHANGED", ErrorCategory.CONFLICT)
            self.pilot.stage_owned(owner, envelope, scope)
            self.validate_sdk(owner, kid, rid, checksum)
            success = True
        except Exception:
            success = False
        with SqlAlchemyUnitOfWork(self.factory) as uow:
            TransferRepository(uow.session).finish(owner, rid, token, success)
        return True

    def change(self, actor: Actor, rid: str, expected: int, action: str) -> dict[str, Any]:
        transitions = {
            "activate": ("VERIFIED", "ACTIVE"),
            "rollback": ("ACTIVE", "VERIFIED"),
            "retry": ("FAILED", "QUEUED"),
        }
        if action not in transitions:
            raise fail("V3_INVALID_ACTION")
        owner = owner_id(actor)
        with SqlAlchemyUnitOfWork(self.factory, read_only=True) as uow:
            row = TransferRepository(uow.session).get(owner, rid)
            if row is None:
                raise fail("V3_TRANSFER_NOT_FOUND", ErrorCategory.NOT_FOUND)
            kid, checksum = row.knowledge_id, row.content_digest
            if row.store_id != self.store_id or row.profile_id != self.profile:
                raise fail("V3_TRANSFER_TARGET_MISMATCH", ErrorCategory.CONFLICT)
        if action == "activate":
            self.validate_sdk(owner, kid, rid, checksum)
        # Both activation and rollback verify retained source; rollback never hides source drift.
        if action in {"activate", "rollback"}:
            original, _ = self.snapshot(owner, kid, rid)
            if digest(serialized(original)) != checksum:
                raise fail("V3_ROLLBACK_SOURCE_CHANGED", ErrorCategory.CONFLICT)
        before, after = transitions[action]
        with SqlAlchemyUnitOfWork(self.factory) as uow:
            # Serialize lifecycle changes with existing source writers.
            if Repository(uow.session).locked_item(owner, kid) is None:
                raise fail("KNOWLEDGE_NOT_FOUND", ErrorCategory.NOT_FOUND)
            if action in {"activate", "rollback"}:
                original, _ = self._snapshot(uow.session, owner, kid, rid)
                if digest(serialized(original)) != checksum:
                    raise fail("V3_SOURCE_CHANGED", ErrorCategory.CONFLICT)
            if not TransferRepository(uow.session).transition(owner, rid, expected, before, after):
                raise fail("V3_TRANSFER_VERSION_CONFLICT", ErrorCategory.CONFLICT)
            uow.session.add(
                Event(
                    owner_id=owner,
                    item_id=kid,
                    revision_id=rid,
                    event_type="V3_" + action.upper(),
                    reason="Explicit source backend transition",
                )
            )
        return self.status(actor, rid)

    def content_owned(self, owner: str, kid: str, rid: str) -> dict[str, Any] | None:
        with SqlAlchemyUnitOfWork(self.factory, read_only=True) as uow:
            row = TransferRepository(uow.session).get(owner, rid)
            if row is None or row.status != "ACTIVE":
                return None
            if row.knowledge_id != kid or row.store_id != self.store_id or row.profile_id != self.profile:
                raise fail("V3_TRANSFER_TARGET_MISMATCH", ErrorCategory.CONFLICT)
            revision = uow.session.get(Revision, rid)
            item = uow.session.get(Item, kid)
            if (
                revision is None
                or item is None
                or revision.owner_id != owner
                or item.owner_id != owner
                or revision.item_id != kid
            ):
                raise fail("KNOWLEDGE_NOT_FOUND", ErrorCategory.NOT_FOUND)
            summary_metadata = summary_view(revision)
            checksum = row.content_digest
        try:
            envelope = self.pilot.read_owned(owner, kid, rid)
            if digest(serialized(envelope)) != checksum:
                raise fail("V3_TRANSFER_INTEGRITY", ErrorCategory.CONFLICT)
            data = envelope.model_dump(mode="json", exclude={"schema_version"})
            return {**summary_metadata, **data}
        except BusinessError:
            raise
        except Exception:
            raise fail("V3_SOURCE_UNAVAILABLE", ErrorCategory.UNAVAILABLE) from None

    def content(self, actor: Actor, kid: str, rid: str) -> dict[str, Any] | None:
        return self.content_owned(owner_id(actor), kid, rid)
