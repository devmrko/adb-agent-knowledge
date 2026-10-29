"""Transaction-scoped audit attribution; no pooled connection session state."""

import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from knowledge_app.audit_models import ChangeContext
from knowledge_app.models import now, uid
from python_foundation.database import SqlAlchemyUnitOfWork
from python_foundation.security import Actor
from python_foundation.web import request_id


@contextmanager
def audited_uow(
    factory: sessionmaker[Session],
    actor: Actor | None,
    operation: str,
    command: Any = None,
    *,
    owner: str | None = None,
) -> Iterator[SqlAlchemyUnitOfWork]:
    with SqlAlchemyUnitOfWork(factory) as uow:
        owner = owner or (
            hashlib.sha256(json.dumps([actor.issuer, actor.subject]).encode()).hexdigest() if actor else None
        )
        if owner is None:
            raise ValueError("Audit owner required")
        context = ChangeContext(
            id=uid(),
            owner_id=owner,
            operation=operation,
            request_id=request_id.get() or uid(),
            actor_subject=actor.subject if actor else None,
            actor_issuer=actor.issuer if actor else None,
            machine_id=getattr(command, "origin_machine_id", None),
            edit_origin=getattr(command, "edit_origin", None),
            reason=getattr(command, "change_note", None) or getattr(command, "reason", None),
            source="APPLICATION" if actor else "WORKER",
            created_at=now(),
        )
        uow.session.add(context)
        uow.session.flush()
        transaction = (
            "DBMS_TRANSACTION.LOCAL_TRANSACTION_ID"
            if uow.session.get_bind().dialect.name == "oracle"
            else "'SQLITE_ACTIVE'"
        )
        uow.session.execute(
            text(f"UPDATE vk_change_context SET transaction_id={transaction} WHERE id=:id"),
            {"id": context.id},
        )
        yield uow
        uow.session.flush()
        uow.session.execute(
            text("UPDATE vk_change_context SET transaction_id=NULL WHERE id=:id"), {"id": context.id}
        )
