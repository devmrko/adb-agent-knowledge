"""Owner-approved configuration, deliberately separate from retrieved knowledge."""

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import DateTime, Integer, String, Text, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from knowledge_app.contracts import normalize_scope
from knowledge_app.models import Base, now
from knowledge_app.service import fail, owner_id
from python_foundation.database import SqlAlchemyUnitOfWork
from python_foundation.errors import ErrorCategory
from python_foundation.security import Actor


class Principle(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    id: str = Field(min_length=1, max_length=60, pattern=r"^[A-Za-z0-9_-]+$")
    title: str = Field(min_length=1, max_length=100)
    instruction: str = Field(min_length=1, max_length=600)
    scope: str = "global"
    enabled: bool = True

    @field_validator("scope")
    @classmethod
    def valid_scope(cls, value: str) -> str:
        value = normalize_scope(value)
        if value != "global" and not value.startswith("project:"):
            raise ValueError("Use global or project scope")
        return value


class PrincipleWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_version: int = Field(ge=0)
    approved: bool
    rules: list[Principle] = Field(max_length=20)
    change_note: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_bundle(self) -> "PrincipleWrite":
        if not self.approved:
            raise ValueError("Explicit approval required")
        if len({r.id for r in self.rules}) != len(self.rules):
            raise ValueError("Duplicate rule IDs")
        if sum(len(r.instruction) for r in self.rules) > 6000:
            raise ValueError("Principle budget exceeded")
        return self


class PrincipleScopes(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scopes: list[str] = Field(min_length=1, max_length=11)

    @field_validator("scopes")
    @classmethod
    def valid_scopes(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(["global", *(Principle.valid_scope(v) for v in values)]))


class PrincipleBundle(Base):
    __tablename__ = "vk_principle_bundle"
    owner_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[int] = mapped_column(Integer)
    rules_json: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PrincipleRevision(Base):
    __tablename__ = "vk_principle_revision"
    owner_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    rules_json: Mapped[str] = mapped_column(Text)
    change_note: Mapped[str] = mapped_column(String(500))
    actor_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PrincipleRepository:
    def __init__(self, session: Session):
        self.session = session

    def current(self, owner: str) -> PrincipleBundle | None:
        return self.session.get(PrincipleBundle, owner)

    def replace(self, owner: str, command: PrincipleWrite) -> int:
        version = command.expected_version + 1
        rules = json.dumps([r.model_dump() for r in command.rules], ensure_ascii=False)
        timestamp = now()
        if command.expected_version == 0:
            self.session.add(
                PrincipleBundle(owner_id=owner, version=version, rules_json=rules, updated_at=timestamp)
            )
        else:
            result = self.session.execute(
                update(PrincipleBundle)
                .where(PrincipleBundle.owner_id == owner, PrincipleBundle.version == command.expected_version)
                .values(version=version, rules_json=rules, updated_at=timestamp)
            )
            if result.rowcount != 1:  # type: ignore[attr-defined]
                raise fail("PRINCIPLE_VERSION_CONFLICT", ErrorCategory.CONFLICT)
        self.session.add(
            PrincipleRevision(
                owner_id=owner,
                version=version,
                rules_json=rules,
                change_note=command.change_note,
                actor_id=owner,
                created_at=timestamp,
            )
        )
        self.session.flush()
        return version

    def history(self, owner: str, offset: int, limit: int) -> list[PrincipleRevision]:
        return list(
            self.session.scalars(
                select(PrincipleRevision)
                .where(PrincipleRevision.owner_id == owner)
                .order_by(PrincipleRevision.version.desc())
                .offset(offset)
                .limit(limit + 1)
            )
        )


class PrincipleService:
    def __init__(self, factory: sessionmaker[Session]):
        self.factory = factory

    def current(self, actor: Actor) -> dict[str, Any]:
        with SqlAlchemyUnitOfWork(self.factory, read_only=True) as uow:
            row = PrincipleRepository(uow.session).current(owner_id(actor))
            return {"version": row.version if row else 0, "rules": json.loads(row.rules_json) if row else []}

    def replace(self, actor: Actor, command: PrincipleWrite) -> dict[str, Any]:
        try:
            with SqlAlchemyUnitOfWork(self.factory) as uow:
                version = PrincipleRepository(uow.session).replace(owner_id(actor), command)
                uow.commit()
                return {"version": version, "status": "READY"}
        except IntegrityError:
            raise fail("PRINCIPLE_VERSION_CONFLICT", ErrorCategory.CONFLICT) from None

    def resolve(self, actor: Actor, command: PrincipleScopes) -> dict[str, Any]:
        bundle = self.current(actor)
        return {
            "status": "READY",
            "version": bundle["version"],
            "scopes": command.scopes,
            "rules": [r for r in bundle["rules"] if r["enabled"] and r["scope"] in command.scopes],
        }

    def history(self, actor: Actor, offset: int, limit: int) -> dict[str, Any]:
        with SqlAlchemyUnitOfWork(self.factory, read_only=True) as uow:
            rows = PrincipleRepository(uow.session).history(owner_id(actor), offset, limit)
            return {
                "items": [
                    {
                        "version": r.version,
                        "rules": json.loads(r.rules_json),
                        "change_note": r.change_note,
                        "actor_id": r.actor_id,
                        "created_at": r.created_at.isoformat(),
                    }
                    for r in rows[:limit]
                ],
                "next_offset": offset + limit if len(rows) > limit else None,
            }
