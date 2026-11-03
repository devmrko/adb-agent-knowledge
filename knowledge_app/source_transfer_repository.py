"""Relational manifest operations; transaction ownership stays in the service."""

from datetime import timedelta

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from knowledge_app.models import SourceTransfer, now, uid


class TransferRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, owner: str, revision: str) -> SourceTransfer | None:
        return self.session.get(SourceTransfer, (owner, revision))

    def claim(self, store_id: str, profile: str) -> tuple[str, str, str] | None:
        current = now()
        eligible = or_(
            SourceTransfer.status == "QUEUED",
            and_(SourceTransfer.status == "PROCESSING", SourceTransfer.lease_until < current),
        )
        row = self.session.scalar(
            select(SourceTransfer)
            .where(
                eligible,
                SourceTransfer.store_id == store_id,
                SourceTransfer.profile_id == profile,
            )
            .order_by(SourceTransfer.updated_at)
            .limit(1)
        )
        if row is None:
            return None
        token = uid()
        result = self.session.execute(
            update(SourceTransfer)
            .where(
                SourceTransfer.owner_id == row.owner_id,
                SourceTransfer.revision_id == row.revision_id,
                SourceTransfer.generation == row.generation,
                eligible,
            )
            .values(
                status="PROCESSING",
                lease_token=token,
                lease_until=current + timedelta(minutes=15),
                attempts=SourceTransfer.attempts + 1,
                generation=SourceTransfer.generation + 1,
                updated_at=current,
                error_code=None,
            )
            .execution_options(synchronize_session=False)
        )
        return (row.owner_id, row.revision_id, token) if result.rowcount == 1 else None  # type: ignore[attr-defined]

    def finish(self, owner: str, revision: str, token: str, success: bool) -> bool:
        result = self.session.execute(
            update(SourceTransfer)
            .where(
                SourceTransfer.owner_id == owner,
                SourceTransfer.revision_id == revision,
                SourceTransfer.status == "PROCESSING",
                SourceTransfer.lease_token == token,
            )
            .values(
                status="VERIFIED" if success else "FAILED",
                error_code=None if success else "V3_STAGE_FAILED",
                lease_token=None,
                lease_until=None,
                generation=SourceTransfer.generation + 1,
                updated_at=now(),
            )
        )
        return result.rowcount == 1  # type: ignore[attr-defined,no-any-return]

    def transition(self, owner: str, revision: str, generation: int, before: str, after: str) -> bool:
        result = self.session.execute(
            update(SourceTransfer)
            .where(
                SourceTransfer.owner_id == owner,
                SourceTransfer.revision_id == revision,
                SourceTransfer.generation == generation,
                SourceTransfer.status == before,
            )
            .values(status=after, generation=SourceTransfer.generation + 1, error_code=None, updated_at=now())
        )
        return result.rowcount == 1  # type: ignore[attr-defined,no-any-return]
