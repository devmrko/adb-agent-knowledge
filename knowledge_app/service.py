import hashlib
import json
import logging
from typing import Any

from sqlalchemy import delete, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from knowledge_app import navigation_rdf, rdf
from knowledge_app.audit_context import audited_uow
from knowledge_app.contracts import (
    ContextRequest,
    CreateKnowledge,
    Provenance,
    RestoreKnowledge,
    RetireKnowledge,
    ReviseKnowledge,
    Search,
)
from knowledge_app.embedding import Embedder, validate_vectors
from knowledge_app.extraction import PPTX_MIME, ExtractionError, extract, fetch_url
from knowledge_app.models import Chunk, Event, Item, Job, Revision, Workflow, now
from knowledge_app.repository import Repository
from knowledge_app.reranking import CrossEncoderReranker, Reranker, validate_scores
from knowledge_app.settings import Settings
from knowledge_app.summaries import extract_summary, summary_view
from knowledge_app.workflow import WorkflowInput
from python_foundation.database import SqlAlchemyUnitOfWork
from python_foundation.errors import BusinessError, ErrorCategory, ErrorSpec
from python_foundation.security import Actor


def owner_id(actor: Actor) -> str:
    return hashlib.sha256(json.dumps([actor.issuer, actor.subject]).encode()).hexdigest()


def fail(code: str, category: ErrorCategory = ErrorCategory.VALIDATION) -> BusinessError:
    return BusinessError(ErrorSpec(code, category, code.replace("_", " ").capitalize()))


def item_view(item: Item) -> dict[str, Any]:
    return dict(
        knowledge_id=item.id,
        title=item.title,
        knowledge_type=item.knowledge_type,
        category=item.category,
        memory_kind=item.memory_kind,
        scope=item.scope,
        lifecycle_status=item.lifecycle_status,
        superseded_by=item.superseded_by_id,
        tags=json.loads(item.tags_json),
        revision_id=item.active_revision_id,
        status="READY" if item.active_revision_id else "PROCESSING",
        created_at=item.created_at.isoformat(),
    )


def provenance_view(revision: Revision) -> dict[str, Any]:
    return dict(
        edit_origin=revision.edit_origin or "UNKNOWN",
        origin_machine_id=revision.origin_machine_id,
        origin_machine_label=revision.origin_machine_label,
        sources=json.loads(revision.sources_json or "[]"),
    )


def provenance_values(command: Provenance, previous: Revision | None = None) -> dict[str, Any]:
    sources = json.loads(previous.sources_json or "[]") if previous else []
    for source in command.sources:
        entry = source.model_dump()
        if entry not in sources:
            sources.append(entry)
    if len(sources) > 100:
        raise fail("TOO_MANY_SOURCES")
    return dict(
        edit_origin=command.edit_origin,
        origin_machine_id=command.origin_machine_id,
        origin_machine_label=command.origin_machine_label,
        sources_json=json.dumps(sources, ensure_ascii=False),
    )


class KnowledgeService:
    def __init__(
        self,
        factory: sessionmaker[Session],
        embedder: Embedder,
        settings: Settings,
        *,
        reranker: Reranker | None = None,
    ) -> None:
        self.factory, self.embedder, self.settings = factory, embedder, settings
        self.reranker = (reranker or CrossEncoderReranker(settings)) if settings.reranker_enabled else None

    def _existing_request(self, actor: Actor, key: str, digest: str) -> dict[str, str] | None:
        with SqlAlchemyUnitOfWork(self.factory, read_only=True) as uow:
            repo = Repository(uow.session)
            item = repo.request_item(owner_id(actor), key)
            if item is None:
                return None
            if item.request_digest != digest:
                raise fail("IDEMPOTENCY_CONFLICT", ErrorCategory.CONFLICT)
            revisions, _ = repo.history(item.owner_id, item.id)
            revision, job = revisions[0]
            assert job is not None
            return dict(knowledge_id=item.id, revision_id=revision.id, job_id=job.id, status=job.status)

    def create(
        self,
        command: CreateKnowledge,
        actor: Actor,
        *,
        data: bytes | None = None,
        filename: str | None = None,
        mime: str = "text/plain",
    ) -> dict[str, str]:
        payload = command.model_dump(exclude={"idempotency_key"})
        if payload.get("summary") is None:
            payload.pop("summary", None)
        for key in ("origin_machine_id", "origin_machine_label", "sources"):
            if not payload[key]:
                payload.pop(key)
        if payload.get("edit_origin") == "API":
            payload.pop("edit_origin")
        payload.update(
            filename=filename,
            mime=mime,
            data_hash=hashlib.sha256(data).hexdigest() if data is not None else None,
        )
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if command.idempotency_key:
            existing = self._existing_request(actor, command.idempotency_key, digest)
            if existing:
                return existing
        try:
            return self._create(command, actor, data=data, filename=filename, mime=mime, digest=digest)
        except IntegrityError:
            if command.idempotency_key:
                existing = self._existing_request(actor, command.idempotency_key, digest)
                if existing:
                    return existing
            raise fail("KNOWLEDGE_CONFLICT", ErrorCategory.CONFLICT) from None

    def _create(
        self,
        command: CreateKnowledge,
        actor: Actor,
        *,
        data: bytes | None = None,
        filename: str | None = None,
        mime: str = "text/plain",
        digest: str,
    ) -> dict[str, str]:
        if sum([command.text is not None, command.url is not None, data is not None]) != 1:
            raise fail("EXACTLY_ONE_SOURCE_REQUIRED")
        owner = owner_id(actor)
        if command.text is not None:
            data = command.text.encode()
        source_limit = (
            self.settings.max_pptx_source_bytes if mime == PPTX_MIME else self.settings.max_source_bytes
        )
        if data is not None and len(data) > source_limit:
            raise fail("SOURCE_TOO_LARGE")
        if mime not in {"text/plain", "text/markdown", "application/pdf", PPTX_MIME}:
            raise fail("UNSUPPORTED_MEDIA")
        with audited_uow(self.factory, actor, "SERVICE_CREATE", command) as uow:
            item = Item(
                owner_id=owner,
                title=command.title,
                knowledge_type=command.knowledge_type,
                memory_kind=command.memory_kind,
                scope=command.scope,
                idempotency_key=command.idempotency_key,
                request_digest=digest,
                request_key_hash=hashlib.sha256(
                    json.dumps([owner, command.idempotency_key]).encode()
                ).hexdigest()
                if command.idempotency_key
                else None,
                category=command.category,
                tags_json=json.dumps(command.tags, ensure_ascii=False),
            )
            uow.session.add(item)
            uow.session.flush()
            revision = Revision(
                owner_id=owner,
                item_id=item.id,
                source_type="URL" if command.url else ("FILE" if filename else "TEXT"),
                source_url=command.url,
                filename=filename,
                mime_type=mime,
                original_data=data,
                summary_text=command.summary,
                summary_kind=command.edit_origin if command.summary else None,
                **provenance_values(command),
            )
            uow.session.add(revision)
            uow.session.flush()
            job = Job(owner_id=owner, revision_id=revision.id)
            uow.session.add(job)
            uow.session.flush()
            uow.session.add(
                Event(owner_id=owner, item_id=item.id, event_type="CREATED", revision_id=revision.id)
            )
            return dict(knowledge_id=item.id, revision_id=revision.id, job_id=job.id, status="QUEUED")

    def set_workflow(
        self, actor: Actor, item_id: str, revision_id: str, command: WorkflowInput
    ) -> dict[str, Any]:
        if not self.settings.workflow_rdf_enabled:
            raise fail("WORKFLOW_DISABLED", ErrorCategory.UNAVAILABLE)
        try:
            with audited_uow(self.factory, actor, "SERVICE_SET_WORKFLOW", command) as uow:
                repo = Repository(uow.session)
                item = repo.locked_item(owner_id(actor), item_id)
                if item is None:
                    raise fail("KNOWLEDGE_NOT_FOUND", ErrorCategory.NOT_FOUND)
                revision = repo.revision(item.owner_id, revision_id)
                if revision is None or revision.item_id != item_id:
                    raise fail("KNOWLEDGE_NOT_FOUND", ErrorCategory.NOT_FOUND)
                history, _ = repo.history(item.owner_id, item_id)
                if (
                    item.lifecycle_status != "ACTIVE"
                    or item.active_revision_id != revision_id
                    or history[-1][0].id != revision_id
                ):
                    raise fail("WORKFLOW_REVISION_CONFLICT", ErrorCategory.CONFLICT)
                if not command.grounded(revision.content_text or ""):
                    raise fail("WORKFLOW_EVIDENCE_MISMATCH")
                existing = uow.session.get(Workflow, revision_id)
                if existing:
                    if existing.owner_id != item.owner_id or existing.payload_hash != command.digest():
                        raise fail("WORKFLOW_IMMUTABLE", ErrorCategory.CONFLICT)
                else:
                    if uow.session.get_bind().dialect.name == "oracle":
                        rdf.insert(uow.session, item.owner_id, revision_id, command)
                        if rdf.read(uow.session, item.owner_id, revision_id).digest() != command.digest():
                            raise fail("WORKFLOW_VERIFY_FAILED", ErrorCategory.UNAVAILABLE)
                    uow.session.add(
                        Workflow(
                            revision_id=revision_id,
                            owner_id=item.owner_id,
                            payload_json=command.canonical(),
                            payload_hash=command.digest(),
                        )
                    )
                return {
                    "status": "READY",
                    "knowledge_id": item_id,
                    "revision_id": revision_id,
                    "storage": "oracle_rdf"
                    if uow.session.get_bind().dialect.name == "oracle"
                    else "sqlite_test",
                }
        except SQLAlchemyError:
            raise fail("WORKFLOW_STORAGE_UNAVAILABLE", ErrorCategory.UNAVAILABLE) from None

    def get_workflow(self, actor: Actor, item_id: str, revision_id: str) -> dict[str, Any]:
        if not self.settings.workflow_rdf_enabled:
            return {"status": "DISABLED"}
        try:
            with SqlAlchemyUnitOfWork(self.factory, read_only=True) as uow:
                repo = Repository(uow.session)
                item = repo.item(owner_id(actor), item_id)
                if item is None:
                    raise fail("KNOWLEDGE_NOT_FOUND", ErrorCategory.NOT_FOUND)
                revision = repo.revision(item.owner_id, revision_id)
                if revision is None or revision.item_id != item_id:
                    raise fail("KNOWLEDGE_NOT_FOUND", ErrorCategory.NOT_FOUND)
                if item.lifecycle_status != "ACTIVE" or item.active_revision_id != revision_id:
                    return {"status": "INACTIVE"}
                manifest = uow.session.get(Workflow, revision_id)
                if manifest is None or manifest.owner_id != item.owner_id:
                    return {"status": "ABSENT"}
                native = uow.session.get_bind().dialect.name == "oracle"
                flow = (
                    rdf.read(uow.session, item.owner_id, revision_id)
                    if native
                    else WorkflowInput.model_validate_json(manifest.payload_json)
                )
                if flow.digest() != manifest.payload_hash:
                    raise fail("WORKFLOW_VERIFY_FAILED", ErrorCategory.UNAVAILABLE)
                return {
                    "status": "READY",
                    "knowledge_id": item_id,
                    "revision_id": revision_id,
                    "storage": "oracle_rdf" if native else "sqlite_test",
                    **flow.model_dump(),
                    "content_uri": f"/api/v1/knowledge/{item_id}/revisions/{revision_id}/content",
                }
        except (SQLAlchemyError, ValueError):
            raise fail("WORKFLOW_STORAGE_UNAVAILABLE", ErrorCategory.UNAVAILABLE) from None

    def categories(self, actor: Actor) -> dict[str, Any]:
        with SqlAlchemyUnitOfWork(self.factory, read_only=True) as uow:
            return {"categories": Repository(uow.session).categories(owner_id(actor))}

    def listing(
        self,
        actor: Actor,
        offset: int,
        limit: int,
        category: str | None,
        memory_kind: str | None = None,
        scope: str | None = None,
        include_retired: bool = False,
        has_relations: bool = False,
    ) -> dict[str, Any]:
        with SqlAlchemyUnitOfWork(self.factory, read_only=True) as uow:
            return {
                "items": [
                    item_view(i)
                    for i in Repository(uow.session).items(
                        owner_id(actor),
                        offset,
                        limit,
                        category,
                        memory_kind,
                        scope,
                        include_retired,
                        has_relations,
                    )
                ],
                "offset": offset,
                "limit": limit,
            }

    def get(self, actor: Actor, item_id: str) -> dict[str, Any]:
        with SqlAlchemyUnitOfWork(self.factory, read_only=True) as uow:
            item = Repository(uow.session).item(owner_id(actor), item_id)
            if item is None:
                raise fail("KNOWLEDGE_NOT_FOUND", ErrorCategory.NOT_FOUND)
            return item_view(item)

    def content(self, actor: Actor, item_id: str, revision_id: str) -> dict[str, Any]:
        with SqlAlchemyUnitOfWork(self.factory, read_only=True) as uow:
            revision = Repository(uow.session).revision(owner_id(actor), revision_id)
            if revision is None or revision.item_id != item_id:
                raise fail("KNOWLEDGE_NOT_FOUND", ErrorCategory.NOT_FOUND)
            if revision.content_text is None:
                raise fail("CONTENT_NOT_READY", ErrorCategory.CONFLICT)
            return dict(
                knowledge_id=item_id,
                revision_id=revision.id,
                text=revision.content_text,
                **summary_view(revision),
                source_url=revision.source_url,
                filename=revision.filename,
                **provenance_view(revision),
            )

    def job(self, actor: Actor, job_id: str) -> dict[str, Any]:
        with SqlAlchemyUnitOfWork(self.factory, read_only=True) as uow:
            job = Repository(uow.session).job(owner_id(actor), job_id)
            if job is None:
                raise fail("JOB_NOT_FOUND", ErrorCategory.NOT_FOUND)
            return dict(job_id=job.id, status=job.status, stage=job.stage, error_code=job.error_code)

    def retry(self, actor: Actor, job_id: str) -> dict[str, str]:
        with audited_uow(self.factory, actor, "SERVICE_RETRY") as uow:
            job = Repository(uow.session).job(owner_id(actor), job_id)
            if job is None:
                raise fail("JOB_NOT_FOUND", ErrorCategory.NOT_FOUND)
            if job.status != "FAILED":
                raise fail("JOB_NOT_FAILED", ErrorCategory.CONFLICT)
            result: Any = uow.session.execute(
                update(Job)
                .where(Job.id == job_id, Job.owner_id == owner_id(actor), Job.status == "FAILED")
                .values(status="QUEUED", stage="WAITING", error_code=None)
            )
            if result.rowcount != 1:
                raise fail("JOB_NOT_FAILED", ErrorCategory.CONFLICT)
        return {"job_id": job_id, "status": "QUEUED"}

    def revise(self, actor: Actor, item_id: str, command: ReviseKnowledge) -> dict[str, str]:
        data = command.text.encode()
        if not command.text.strip():
            raise fail("BLANK_TEXT")
        if len(data) > self.settings.max_source_bytes:
            raise fail("SOURCE_TOO_LARGE")
        owner = owner_id(actor)
        try:
            with audited_uow(self.factory, actor, "SERVICE_REVISE", command) as uow:
                repo = Repository(uow.session)
                item = repo.locked_item(owner, item_id)
                if item is None:
                    raise fail("KNOWLEDGE_NOT_FOUND", ErrorCategory.NOT_FOUND)
                if item.lifecycle_status != "ACTIVE":
                    raise fail("KNOWLEDGE_RETIRED", ErrorCategory.CONFLICT)
                revisions, _ = repo.history(owner, item_id)
                if revisions[-1][0].id != str(command.expected_revision_id):
                    raise fail("REVISION_CONFLICT", ErrorCategory.CONFLICT)
                previous = repo.revision(owner, item.active_revision_id) if item.active_revision_id else None
                revision = Revision(
                    owner_id=owner,
                    item_id=item_id,
                    revision_no=revisions[-1][0].revision_no + 1,
                    change_note=command.change_note,
                    original_data=data,
                    source_type="TEXT",
                    mime_type="text/plain",
                    summary_text=command.summary,
                    summary_kind=command.edit_origin if command.summary else None,
                    **provenance_values(command, previous),
                )
                uow.session.add(revision)
                uow.session.flush()
                job = Job(owner_id=owner, revision_id=revision.id)
                uow.session.add(job)
                uow.session.add(
                    Event(
                        owner_id=owner,
                        item_id=item_id,
                        event_type="REVISED",
                        revision_id=revision.id,
                        reason=command.change_note,
                    )
                )
                item.updated_at = now()
                uow.session.flush()
                return dict(knowledge_id=item_id, revision_id=revision.id, job_id=job.id, status="QUEUED")
        except IntegrityError:
            raise fail("REVISION_CONFLICT", ErrorCategory.CONFLICT) from None

    def retire(self, actor: Actor, item_id: str, command: RetireKnowledge) -> dict[str, Any]:
        owner = owner_id(actor)
        if not command.reason.strip():
            raise fail("BLANK_REASON")
        with audited_uow(self.factory, actor, "SERVICE_RETIRE", command) as uow:
            repo = Repository(uow.session)
            item = repo.locked_item(owner, item_id)
            if item is None:
                raise fail("KNOWLEDGE_NOT_FOUND", ErrorCategory.NOT_FOUND)
            target_id = str(command.superseded_by) if command.superseded_by else None
            if target_id:
                target = repo.item(owner, target_id)
                if target is None:
                    raise fail("KNOWLEDGE_NOT_FOUND", ErrorCategory.NOT_FOUND)
                if target_id == item_id or target.lifecycle_status != "ACTIVE" or target.scope != item.scope:
                    raise fail("INVALID_REPLACEMENT")
            if not repo.set_lifecycle(
                owner,
                item_id,
                "ACTIVE",
                lifecycle_status="RETIRED",
                retired_at=now(),
                superseded_by_id=target_id,
            ):
                raise fail("LIFECYCLE_CONFLICT", ErrorCategory.CONFLICT)
            uow.session.add(
                Event(
                    owner_id=owner,
                    item_id=item_id,
                    event_type="RETIRED",
                    revision_id=item.active_revision_id,
                    related_item_id=target_id,
                    reason=command.reason,
                )
            )
            return item_view(item)

    def restore(self, actor: Actor, item_id: str, command: RestoreKnowledge) -> dict[str, Any]:
        owner = owner_id(actor)
        with audited_uow(self.factory, actor, "SERVICE_RESTORE", command) as uow:
            repo = Repository(uow.session)
            item = repo.locked_item(owner, item_id)
            if item is None:
                raise fail("KNOWLEDGE_NOT_FOUND", ErrorCategory.NOT_FOUND)
            if not repo.set_lifecycle(
                owner, item_id, "RETIRED", lifecycle_status="ACTIVE", retired_at=None, superseded_by_id=None
            ):
                raise fail("LIFECYCLE_CONFLICT", ErrorCategory.CONFLICT)
            uow.session.add(
                Event(
                    owner_id=owner,
                    item_id=item_id,
                    event_type="RESTORED",
                    revision_id=item.active_revision_id,
                    reason=command.reason,
                )
            )
            return item_view(item)

    def history(self, actor: Actor, item_id: str) -> dict[str, Any]:
        with SqlAlchemyUnitOfWork(self.factory, read_only=True) as uow:
            repo = Repository(uow.session)
            item = repo.item(owner_id(actor), item_id)
            if item is None:
                raise fail("KNOWLEDGE_NOT_FOUND", ErrorCategory.NOT_FOUND)
            revisions, events = repo.history(item.owner_id, item_id)
            return dict(
                item=item_view(item),
                revisions=[
                    dict(
                        revision_id=r.id,
                        revision_no=r.revision_no,
                        change_note=r.change_note,
                        **provenance_view(r),
                        created_at=r.created_at.isoformat(),
                        status=j.status if j else "UNKNOWN",
                        active=r.id == item.active_revision_id,
                    )
                    for r, j in revisions
                ],
                events=[
                    dict(
                        event_id=e.id,
                        event_type=e.event_type,
                        revision_id=e.revision_id,
                        related_item_id=e.related_item_id,
                        reason=e.reason,
                        created_at=e.created_at.isoformat(),
                    )
                    for e in events
                ],
            )

    def context(self, actor: Actor, command: ContextRequest) -> dict[str, Any]:
        found = self.search(actor, Search.model_validate(command.model_dump(exclude={"max_chars"})))
        entries = []
        remaining = command.max_chars
        for item in found["items"]:
            for match in item["matches"]:
                if remaining <= 0:
                    break
                excerpt = match["text"][:remaining]
                remaining -= len(excerpt)
                entries.append(
                    dict(
                        title=item["title"],
                        knowledge_id=item["knowledge_id"],
                        revision_id=item["revision_id"],
                        memory_kind=item["memory_kind"],
                        scope=item["scope"],
                        text=excerpt,
                        location=match["location"],
                        truncated=len(excerpt) < len(match["text"]),
                    )
                )
        return dict(
            entries=entries,
            used_chars=command.max_chars - remaining,
            max_chars=command.max_chars,
            format="source_excerpts",
            generated_summary=False,
            profile_id=found["profile_id"],
        )

    def search(self, actor: Actor, command: Search) -> dict[str, Any]:
        result = self._search(actor, command)
        with SqlAlchemyUnitOfWork(self.factory, read_only=True) as uow:
            repo = Repository(uow.session)
            for item in result["items"]:
                revision = repo.revision(owner_id(actor), item["revision_id"])
                if revision:
                    item.update(summary_view(revision))
        return result

    def refresh_derived(self, actor: Actor, item_id: str) -> dict[str, Any]:
        with audited_uow(self.factory, actor, "SERVICE_REFRESH_DERIVED") as uow:
            owner = owner_id(actor)
            repo = Repository(uow.session)
            item = repo.locked_item(owner, item_id)
            if not item:
                raise fail("KNOWLEDGE_NOT_FOUND", ErrorCategory.NOT_FOUND)
            if item.lifecycle_status != "ACTIVE" or not item.active_revision_id:
                raise fail("CONTENT_NOT_READY", ErrorCategory.CONFLICT)
            revision = repo.revision(owner, item.active_revision_id)
            assert revision is not None
            if not revision.content_text:
                raise fail("CONTENT_NOT_READY", ErrorCategory.CONFLICT)
            if not revision.summary_text:
                revision.summary_text = extract_summary(revision.content_text)
                revision.summary_kind = "EXTRACTIVE"
            navigation_rdf.store(
                uow.session,
                owner,
                revision.id,
                navigation_rdf.revision_rows(revision, item.scope, item.memory_kind),
                self.settings.workflow_rdf_enabled,
            )
            return {"knowledge_id": item.id, "revision_id": revision.id, **summary_view(revision)}

    def original(self, actor: Actor, item_id: str, revision_id: str) -> tuple[bytes, str, str]:
        with SqlAlchemyUnitOfWork(self.factory, read_only=True) as uow:
            revision = Repository(uow.session).revision(owner_id(actor), revision_id)
            if not revision or revision.item_id != item_id or revision.original_data is None:
                raise fail("ORIGINAL_NOT_FOUND", ErrorCategory.NOT_FOUND)
            return revision.original_data, revision.mime_type, revision.filename or "source.txt"

    def summary(self, actor: Actor, item_id: str, revision_id: str) -> dict[str, Any]:
        with SqlAlchemyUnitOfWork(self.factory, read_only=True) as uow:
            revision = Repository(uow.session).revision(owner_id(actor), revision_id)
            if not revision or revision.item_id != item_id:
                raise fail("KNOWLEDGE_NOT_FOUND", ErrorCategory.NOT_FOUND)
            if revision.content_text is None:
                raise fail("CONTENT_NOT_READY", ErrorCategory.CONFLICT)
            return {
                "knowledge_id": item_id,
                "revision_id": revision_id,
                **summary_view(revision),
                "content_uri": f"/api/v1/knowledge/{item_id}/revisions/{revision_id}/content",
            }

    def _search(self, actor: Actor, command: Search) -> dict[str, Any]:
        with SqlAlchemyUnitOfWork(self.factory, read_only=True) as uow:
            if Repository(uow.session).incompatible_profile(
                owner_id(actor), self.embedder.profile_id, command
            ):
                raise fail("EMBEDDING_PROFILE_MISMATCH", ErrorCategory.CONFLICT)
        try:
            vectors = self.embedder.encode([command.query], query=True)
            validate_vectors(vectors, 1, self.embedder.dimensions)
        except Exception as error:
            raise fail("EMBEDDING_UNAVAILABLE", ErrorCategory.UNAVAILABLE) from error
        if self.reranker is not None:
            return self._search_reranked(actor, command, vectors[0])
        with SqlAlchemyUnitOfWork(self.factory, read_only=True) as uow:
            rows = Repository(uow.session).candidates(
                owner_id(actor), self.embedder.profile_id, vectors[0], command
            )
            result: dict[str, dict[str, Any]] = {}
            threshold = (
                command.min_similarity
                if command.min_similarity is not None
                else self.settings.search_min_similarity
            )
            excluded = set()
            eligible = {r.item.id for r in rows if r.similarity >= threshold or r.keyword_coverage >= 1.0}
            for row in rows:
                chunk, item, score = row.chunk, row.item, row.rank_score
                if row.similarity < threshold and row.keyword_coverage < 1.0:
                    excluded.add(item.id)
                    continue
                if item.id not in result:
                    if len(result) >= command.top_k:
                        continue
                    result[item.id] = {
                        **item_view(item),
                        "score": score,
                        "similarity": row.similarity,
                        "keyword_coverage": row.keyword_coverage,
                        "matches": [],
                        "content_uri": f"/api/v1/knowledge/{item.id}/revisions/{chunk.revision_id}/content",
                    }
                result[item.id]["similarity"] = max(result[item.id]["similarity"], row.similarity)
                result[item.id]["keyword_coverage"] = max(
                    result[item.id]["keyword_coverage"], row.keyword_coverage
                )
                if len(result[item.id]["matches"]) < 3:
                    result[item.id]["matches"].append(
                        dict(
                            chunk_id=chunk.id,
                            text=chunk.text,
                            location=dict(
                                page=chunk.page_no,
                                source_part=chunk.source_part,
                                char_start=chunk.char_start,
                                char_end=chunk.char_end,
                            ),
                        )
                    )
            return {
                "items": list(result.values()),
                "profile_id": self.embedder.profile_id,
                "score_type": "rrf",
                "min_similarity": threshold,
                "excluded_count": len(excluded - eligible),
            }

    def _search_reranked(self, actor: Actor, command: Search, vector: list[float]) -> dict[str, Any]:
        candidates: dict[str, dict[str, Any]] = {}
        with SqlAlchemyUnitOfWork(self.factory, read_only=True) as uow:
            rows = Repository(uow.session).candidates(
                owner_id(actor), self.embedder.profile_id, vector, command
            )
            for row in rows:
                item, chunk = row.item, row.chunk
                if item.id not in candidates:
                    if len(candidates) >= self.settings.reranker_candidates:
                        continue
                    candidates[item.id] = {
                        **item_view(item),
                        "rrf_score": row.rank_score,
                        "matches": [],
                        "content_uri": f"/api/v1/knowledge/{item.id}/revisions/{chunk.revision_id}/content",
                    }
                if len(candidates[item.id]["matches"]) < 3:
                    candidates[item.id]["matches"].append(
                        {
                            "chunk_id": chunk.id,
                            "text": chunk.text,
                            "similarity": row.similarity,
                            "keyword_coverage": row.keyword_coverage,
                            "location": dict(
                                page=chunk.page_no,
                                source_part=chunk.source_part,
                                char_start=chunk.char_start,
                                char_end=chunk.char_end,
                            ),
                        }
                    )
        # Copy source fields while the session is open; release DB connection before inference.
        pairs = [(item, match) for item in candidates.values() for match in item["matches"]]
        passages = [item["title"] + "\n" + match["text"] for item, match in pairs]
        try:
            assert self.reranker is not None
            scores = self.reranker.score(command.query, passages) if passages else []
            validate_scores(scores, len(passages))
        except Exception as error:
            raise fail("RERANKER_UNAVAILABLE", ErrorCategory.UNAVAILABLE) from error
        for (_, match), score in zip(pairs, scores, strict=True):
            match["rerank_score"] = score
        accepted = []
        for document in candidates.values():
            matches = [
                m
                for m in document["matches"]
                if m["rerank_score"] >= self.settings.reranker_min_score
                and (command.min_similarity is None or m["similarity"] >= command.min_similarity)
            ]
            if not matches:
                continue
            document["matches"] = sorted(matches, key=lambda m: -m["rerank_score"])
            document["score"] = document["rerank_score"] = document["matches"][0]["rerank_score"]
            document["similarity"] = max(m["similarity"] for m in matches)
            document["keyword_coverage"] = max(m["keyword_coverage"] for m in matches)
            accepted.append(document)
        accepted.sort(key=lambda item: -item["score"])
        return {
            "items": accepted[: command.top_k],
            "profile_id": self.embedder.profile_id,
            "score_type": "reranker_sigmoid",
            "min_similarity": command.min_similarity,
            "excluded_count": len(candidates) - len(accepted),
            "reranker": {
                "model": self.settings.reranker_model,
                "revision": self.settings.reranker_revision,
                "device": self.settings.reranker_device,
                "max_length": self.settings.reranker_max_length,
                "candidate_limit": self.settings.reranker_candidates,
                "candidate_count": len(candidates),
                "pair_count": len(pairs),
                "min_score": self.settings.reranker_min_score,
            },
        }

    def process_one(self) -> bool:
        with SqlAlchemyUnitOfWork(self.factory) as uow:
            job_id = Repository(uow.session).claim()
        if job_id is None:
            return False
        try:
            with SqlAlchemyUnitOfWork(self.factory, read_only=True) as uow:
                job = uow.session.get(Job, job_id)
                assert job is not None
                revision = Repository(uow.session).revision(job.owner_id, job.revision_id)
                assert revision is not None
                owner, revision_id = job.owner_id, revision.id
                data, mime = revision.original_data, revision.mime_type
                source_url = revision.source_url
            if source_url:
                hosts = {h.strip().lower() for h in self.settings.url_allowed_hosts.split(",") if h.strip()}
                data, mime = fetch_url(source_url, hosts, self.settings.max_source_bytes)
            assert data is not None
            content = extract(data, mime, self.settings.max_text_chars)
            pieces = self.embedder.split(content)
            if not pieces:
                raise ExtractionError("NO_TEXT")
            vectors = self.embedder.encode([piece.text for piece in pieces])
            validate_vectors(vectors, len(pieces), self.embedder.dimensions)
            with audited_uow(self.factory, None, "SOURCE_ACTIVATED", owner=owner) as uow:
                repo = Repository(uow.session)
                revision = repo.revision(owner, revision_id)
                job = repo.job(owner, job_id)
                assert revision is not None and job is not None
                item = repo.locked_item(owner, revision.item_id)
                assert item is not None
                uow.session.execute(
                    delete(Chunk).where(Chunk.owner_id == owner, Chunk.revision_id == revision_id)
                )
                for index, (piece, vector) in enumerate(zip(pieces, vectors, strict=True)):
                    uow.session.add(
                        Chunk(
                            owner_id=owner,
                            revision_id=revision_id,
                            chunk_no=index,
                            source_part=piece.source_part,
                            text=piece.text,
                            page_no=piece.page,
                            char_start=piece.start,
                            char_end=piece.end,
                            profile_id=self.embedder.profile_id,
                            embedding=vector,
                        )
                    )
                revision.content_text, revision.original_data, revision.mime_type = content, data, mime
                if not revision.summary_text:
                    revision.summary_text = extract_summary(content)
                    revision.summary_kind = "EXTRACTIVE"
                active = repo.revision(owner, item.active_revision_id) if item.active_revision_id else None
                if active is None or revision.revision_no > active.revision_no:
                    item.active_revision_id = revision.id
                    if self.settings.workflow_rdf_enabled:
                        from knowledge_app.graph_ops_repository import GraphOpsRepository

                        GraphOpsRepository(uow.session).ensure_review(owner, item.id, revision.id)
                    uow.session.add(
                        Event(
                            owner_id=owner,
                            item_id=item.id,
                            event_type="SOURCE_ACTIVATED",
                            revision_id=revision.id,
                        )
                    )
                navigation_rdf.store(
                    uow.session,
                    owner,
                    revision.id,
                    navigation_rdf.revision_rows(revision, item.scope, item.memory_kind),
                    self.settings.workflow_rdf_enabled,
                )
                job.status, job.stage = "READY", "COMPLETE"
        except Exception as error:
            logging.getLogger("python_foundation.worker").error(
                "Ingestion failed type=%s job=%s", type(error).__name__, job_id
            )
            with SqlAlchemyUnitOfWork(self.factory) as uow:
                job = uow.session.get(Job, job_id)
                assert job is not None
                job.status = "FAILED"
                job.error_code = str(error) if isinstance(error, ExtractionError) else "PROCESSING_FAILED"
        return True
