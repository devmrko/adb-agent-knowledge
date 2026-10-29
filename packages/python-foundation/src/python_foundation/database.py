"""Synchronous SQLAlchemy infrastructure; one session per service unit of work."""

from abc import ABC, abstractmethod
from collections.abc import Callable
from types import TracebackType
from typing import Any, Protocol, Self

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool

from python_foundation.settings import FoundationSettings


class UnitOfWork(Protocol):
    """Explicit service transaction boundary; repositories never commit."""

    def __enter__(self) -> Self: ...
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...


class AbstractUnitOfWork(ABC):
    """Commit on success, rollback on any failure, always close.

    Instances are single-use. Reuse a factory for independent operations.
    For nested services, explicitly pass the active UoW; there is no implicit REQUIRED propagation.
    """

    @abstractmethod
    def commit(self) -> None: ...

    @abstractmethod
    def rollback(self) -> None: ...

    @abstractmethod
    def close(self) -> None: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            if exc_type is None:
                try:
                    self.commit()
                except BaseException:
                    self.rollback()
                    raise
            else:
                self.rollback()
        finally:
            self.close()


class SqlAlchemyUnitOfWork(AbstractUnitOfWork):
    """Owns a SQLAlchemy Session; never share this instance across threads/tasks."""

    def __init__(self, factory: Callable[[], Session], *, read_only: bool = False) -> None:
        self._factory = factory
        self._read_only = read_only
        self._used = False
        self.session: Session

    def __enter__(self) -> Self:
        if self._used:
            raise RuntimeError("UnitOfWork instances are single-use")
        self._used = True
        self.session = self._factory()
        try:
            if self._read_only:
                event.listen(self.session, "before_flush", self._reject_flush)
            self.session.begin()
        except BaseException:
            self.session.close()
            raise
        return self

    @staticmethod
    def _reject_flush(session: Session, flush_context: Any, instances: Any) -> None:
        if session.new or session.dirty or session.deleted:
            raise RuntimeError("Cannot flush ORM changes in a read-only UnitOfWork")

    def commit(self) -> None:
        if self._read_only:
            self._reject_flush(self.session, None, None)
            self.session.rollback()
        else:
            self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()

    def close(self) -> None:
        self.session.close()


def create_database(settings: FoundationSettings) -> Engine:
    """Uses one SQLAlchemy QueuePool; does not layer an Oracle driver pool on top."""
    url = make_url(settings.database_url.get_secret_value())
    if url.get_backend_name() == "sqlite" and url.database in (None, "", ":memory:"):
        raise ValueError("Use a file-backed SQLite database; pooled in-memory databases are not supported")
    engine = create_engine(
        url,
        poolclass=QueuePool,
        pool_size=settings.pool_size,
        max_overflow=0,
        pool_timeout=settings.pool_timeout,
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={"check_same_thread": False} if url.get_backend_name() == "sqlite" else {},
    )
    if url.get_backend_name() == "sqlite":

        @event.listens_for(engine, "connect")
        def sqlite_settings(connection: Any, record: Any) -> None:
            cursor = connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute(f"PRAGMA busy_timeout={settings.sqlite_busy_timeout_ms}")
            finally:
                cursor.close()

    return engine


def sessions(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)
