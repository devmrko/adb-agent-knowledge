import json
import math
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, bindparam, case, func, literal, literal_column, or_, select, update
from sqlalchemy.orm import Session
from sqlalchemy.sql.selectable import Exists

from knowledge_app.contracts import Search
from knowledge_app.models import (
    Chunk,
    Event,
    GraphClaim,
    GraphEvidence,
    GraphVersion,
    Item,
    Job,
    Revision,
    SourceTransfer,
    Vector,
    now,
)
from knowledge_app.sdk_search import sdk_chunk_model, sdk_chunks


@dataclass
class Candidate:
    chunk: Chunk
    item: Item
    rank_score: float
    similarity: float
    keyword_coverage: float


def query_terms(query: str) -> list[str]:
    return list(dict.fromkeys(query.casefold().split()))[:8]


def has_active_relations() -> Exists:
    return (
        select(GraphEvidence.id)
        .join(
            GraphVersion,
            (GraphVersion.id == GraphEvidence.version_id) & (GraphVersion.owner_id == GraphEvidence.owner_id),
        )
        .join(
            GraphClaim,
            (GraphClaim.current_version_id == GraphVersion.id)
            & (GraphClaim.owner_id == GraphVersion.owner_id)
            & (GraphClaim.id == GraphVersion.claim_id),
        )
        .where(
            GraphEvidence.owner_id == Item.owner_id,
            GraphEvidence.knowledge_id == Item.id,
            GraphEvidence.revision_id == Item.active_revision_id,
            Item.lifecycle_status == "ACTIVE",
            GraphVersion.status == "ACTIVE",
            GraphVersion.recorded_to.is_(None),
        )
        .correlate(Item)
        .exists()
    )


class Repository:
    def __init__(self, session: Session, *, sdk_store_id: str | None = None) -> None:
        self.session = session
        self.sdk_store_id = sdk_store_id

    def item(self, owner: str, item_id: str) -> Item | None:
        return self.session.scalar(select(Item).where(Item.owner_id == owner, Item.id == item_id))

    def locked_item(self, owner: str, item_id: str) -> Item | None:
        return self.session.scalar(
            select(Item)
            .where(Item.owner_id == owner, Item.id == item_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    def request_item(self, owner: str, key: str) -> Item | None:
        return self.session.scalar(select(Item).where(Item.owner_id == owner, Item.idempotency_key == key))

    def revision(self, owner: str, revision_id: str) -> Revision | None:
        return self.session.scalar(
            select(Revision).where(Revision.owner_id == owner, Revision.id == revision_id)
        )

    def job(self, owner: str, job_id: str) -> Job | None:
        return self.session.scalar(select(Job).where(Job.owner_id == owner, Job.id == job_id))

    def categories(self, owner: str) -> list[str]:
        return list(
            self.session.scalars(
                select(Item.category)
                .where(
                    Item.owner_id == owner,
                    Item.lifecycle_status == "ACTIVE",
                    Item.category.is_not(None),
                )
                .distinct()
                .order_by(Item.category)
            )
        )

    def items(
        self,
        owner: str,
        offset: int,
        limit: int,
        category: str | None,
        memory_kind: str | None = None,
        scope: str | None = None,
        include_retired: bool = True,
        has_relations: bool = False,
    ) -> list[Item]:
        statement = select(Item).where(Item.owner_id == owner)
        if has_relations:
            statement = statement.where(has_active_relations())
        if category is not None:
            statement = statement.where(Item.category == category)
        if memory_kind is not None:
            statement = statement.where(Item.memory_kind == memory_kind)
        if scope is not None:
            statement = statement.where(Item.scope == scope)
        if not include_retired:
            statement = statement.where(Item.lifecycle_status == "ACTIVE")
        return list(
            self.session.scalars(
                statement.order_by(Item.created_at.desc(), Item.id).offset(offset).limit(limit)
            )
        )

    def next_revision_no(self, owner: str, item_id: str) -> int:
        current = self.session.scalar(
            select(func.max(Revision.revision_no)).where(
                Revision.owner_id == owner, Revision.item_id == item_id
            )
        )
        return int(current or 0) + 1

    def history(self, owner: str, item_id: str) -> tuple[list[tuple[Revision, Job | None]], list[Event]]:
        revisions = list(
            self.session.execute(
                select(Revision, Job)
                .outerjoin(Job, (Job.revision_id == Revision.id) & (Job.owner_id == Revision.owner_id))
                .where(Revision.owner_id == owner, Revision.item_id == item_id)
                .order_by(Revision.revision_no)
            ).tuples()
        )
        events = list(
            self.session.scalars(
                select(Event)
                .where(Event.owner_id == owner, Event.item_id == item_id)
                .order_by(Event.created_at, Event.id)
            )
        )
        return [(r, j) for r, j in revisions], events

    def set_lifecycle(self, owner: str, item_id: str, expected: str, **values: Any) -> bool:
        result: Any = self.session.execute(
            update(Item)
            .where(Item.owner_id == owner, Item.id == item_id, Item.lifecycle_status == expected)
            .values(updated_at=now(), **values)
        )
        return bool(result.rowcount == 1)

    def claim(self) -> str | None:
        ids = list(
            self.session.scalars(
                select(Job.id).where(Job.status == "QUEUED").order_by(Job.created_at).limit(10)
            )
        )
        for job_id in ids:
            result: Any = self.session.execute(
                update(Job)
                .where(Job.id == job_id, Job.status == "QUEUED")
                .values(status="RUNNING", stage="EXTRACTING", started_at=now())
            )
            if result.rowcount == 1:
                return job_id
        return None

    def incompatible_profile(self, owner: str, profile: str, command: Search) -> bool:
        statement = (
            select(Chunk.id)
            .join(Item, (Item.active_revision_id == Chunk.revision_id) & (Item.owner_id == Chunk.owner_id))
            .where(Chunk.owner_id == owner, Chunk.profile_id != profile)
        )
        if not command.include_retired:
            statement = statement.where(Item.lifecycle_status == "ACTIVE")
        if command.scopes is not None:
            statement = statement.where(Item.scope.in_(command.scopes))
        if command.category is not None:
            statement = statement.where(Item.category == command.category)
        if command.knowledge_type is not None:
            statement = statement.where(Item.knowledge_type == command.knowledge_type)
        if command.memory_kinds is not None:
            statement = statement.where(Item.memory_kind.in_(command.memory_kinds))
        if command.has_relations:
            statement = statement.where(has_active_relations())
        return self.session.scalar(statement.limit(1)) is not None

    def sdk_incomplete(self, owner: str, profile: str, command: Search) -> bool:
        if self.sdk_store_id is None:
            return False
        sdk = sdk_chunks(self.sdk_store_id)
        statement = (
            select(Chunk.id)
            .join(Item, (Item.owner_id == Chunk.owner_id) & (Item.active_revision_id == Chunk.revision_id))
            .outerjoin(
                SourceTransfer,
                (SourceTransfer.owner_id == Chunk.owner_id)
                & (SourceTransfer.revision_id == Chunk.revision_id),
            )
            .outerjoin(
                sdk,
                (sdk.c.source_id == SourceTransfer.sdk_record_id)
                & (sdk.c.user_id == Chunk.owner_id)
                & (sdk.c.source_record_type == "memory")
                & (sdk.c.chunk_seq == Chunk.chunk_no + 1),
            )
            .where(
                Chunk.owner_id == owner,
                or_(
                    SourceTransfer.status.is_(None),
                    SourceTransfer.status != "ACTIVE",
                    SourceTransfer.store_id != self.sdk_store_id,
                    SourceTransfer.profile_id != profile,
                    sdk.c.source_id.is_(None),
                    sdk.c.embedding.is_(None),
                    sdk.c.chunk_text.is_(None),
                ),
            )
        )
        if command.has_relations:
            statement = statement.where(has_active_relations())
        if command.category is not None:
            statement = statement.where(Item.category == command.category)
        if command.knowledge_type is not None:
            statement = statement.where(Item.knowledge_type == command.knowledge_type)
        if command.memory_kinds is not None:
            statement = statement.where(Item.memory_kind.in_(command.memory_kinds))
        if command.scopes is not None:
            statement = statement.where(Item.scope.in_(command.scopes))
        if not command.include_retired:
            statement = statement.where(Item.lifecycle_status == "ACTIVE")
        return self.session.scalar(statement.limit(1)) is not None

    def candidates(self, owner: str, profile: str, vector: list[float], command: Search) -> list[Candidate]:
        chunk_model = sdk_chunk_model(self.sdk_store_id) if self.sdk_store_id else Chunk
        statement: Select[Any] = (
            select(chunk_model, Item)
            .join(
                Revision,
                (Revision.id == chunk_model.revision_id) & (Revision.owner_id == chunk_model.owner_id),
            )
            .join(Item, (Item.id == Revision.item_id) & (Item.owner_id == Revision.owner_id))
            .where(
                chunk_model.owner_id == owner,
                chunk_model.profile_id == profile,
                Item.active_revision_id == Revision.id,
            )
        )
        if command.has_relations:
            statement = statement.where(has_active_relations())
        if command.category is not None:
            statement = statement.where(Item.category == command.category)
        if command.knowledge_type is not None:
            statement = statement.where(Item.knowledge_type == command.knowledge_type)
        if command.memory_kinds is not None:
            statement = statement.where(Item.memory_kind.in_(command.memory_kinds))
        if command.scopes is not None:
            statement = statement.where(Item.scope.in_(command.scopes))
        if not command.include_retired:
            statement = statement.where(Item.lifecycle_status == "ACTIVE")
        oracle = self.session.bind is not None and self.session.bind.dialect.name == "oracle"
        params: dict[str, Any] = {}
        vector_rows: list[Any]
        if oracle:
            # SDK 26.8 stores JSON-derived vectors as FLOAT64, while our query bind is FLOAT32.
            # Normalize the stored value for exact search; never compare differing vector formats.
            stored_vector = (
                func.to_vector(chunk_model.embedding, literal_column("1024"), literal_column("FLOAT32"))
                if self.sdk_store_id
                else chunk_model.embedding
            )
            distance = func.vector_distance(
                stored_vector, bindparam("query_vector", type_=Vector()), literal_column("COSINE")
            )
            statement = statement.add_columns(distance)
            params["query_vector"] = vector
            vector_rows = list(
                self.session.execute(statement.order_by(distance, chunk_model.id).limit(100), params).all()
            )
        else:
            vector_rows = [
                (chunk, item, self.distance(chunk.embedding, vector))
                for chunk, item in self.session.execute(statement).all()
            ]
            vector_rows.sort(key=lambda row: (row[2], row[0].id))
            vector_rows = vector_rows[:100]
        terms = query_terms(command.query)
        scores: dict[str, Candidate] = {}

        def add(chunk: Chunk, item: Item, distance: float, rank: int) -> None:
            previous = scores.get(chunk.id)
            if previous is not None:
                previous.rank_score += 1 / (60 + rank)
                return
            haystack = " ".join([chunk.text, item.title, " ".join(json.loads(item.tags_json))]).casefold()
            coverage = sum(term in haystack for term in terms) / len(terms) if terms else 0.0
            scores[chunk.id] = Candidate(chunk, item, 1 / (60 + rank), 1 - float(distance), coverage)

        for rank, (chunk, item, distance) in enumerate(vector_rows, 1):
            add(chunk, item, distance, rank)
        # Literal substring keyword candidates, independently scoped BEFORE ranking.
        if terms:
            predicates = []
            for term in terms:
                predicates.extend(
                    [
                        func.lower(chunk_model.text).contains(term, autoescape=True),
                        func.lower(Item.title).contains(term, autoescape=True),
                        func.lower(Item.tags_json).contains(term, autoescape=True),
                    ]
                )
            keyword_statement = statement.where(or_(*predicates)).order_by(
                sum((case((p, 1), else_=0) for p in predicates), literal(0)).desc(), chunk_model.id
            )
            keyword_rows: list[Any] = list(self.session.execute(keyword_statement.limit(100), params).all())
            if not oracle:
                distances = {chunk.id: distance for chunk, _, distance in vector_rows}
                keyword_rows = [
                    (chunk, item, distances.get(chunk.id, self.distance(chunk.embedding, vector)))
                    for chunk, item in keyword_rows
                ]
            for rank, (chunk, item, distance) in enumerate(keyword_rows, 1):
                add(chunk, item, distance, rank)
        return sorted(scores.values(), key=lambda row: (-row.rank_score, row.chunk.id))

    @staticmethod
    def distance(left: list[float], right: list[float]) -> float:
        norm = math.sqrt(sum(x * x for x in left)) * math.sqrt(sum(x * x for x in right))
        return 1 - sum(a * b for a, b in zip(left, right, strict=True)) / norm
