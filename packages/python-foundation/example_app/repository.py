"""Repository implements persistence operations, never transaction commit."""

from typing import Protocol, Self

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from example_app.models import Project
from python_foundation.database import SqlAlchemyUnitOfWork


class ProjectRepository(Protocol):
    def find(self, project_id: str) -> Project | None: ...
    def create(self, name: str) -> Project: ...
    def list(self, page: int, size: int) -> list[Project]: ...
    def count(self) -> int: ...
    def delete(self, project: Project) -> None: ...
    def flush(self) -> None: ...


class SqlProjectRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find(self, project_id: str) -> Project | None:
        return self.session.get(Project, project_id)

    def create(self, name: str) -> Project:
        project = Project(name=name)
        self.session.add(project)
        self.session.flush()
        return project

    def list(self, page: int, size: int) -> list[Project]:
        return list(
            self.session.scalars(select(Project).order_by(Project.id).offset(page * size).limit(size))
        )

    def count(self) -> int:
        return self.session.scalar(select(func.count()).select_from(Project)) or 0

    def delete(self, project: Project) -> None:
        self.session.delete(project)

    def flush(self) -> None:
        self.session.flush()


class ProjectUnitOfWork(SqlAlchemyUnitOfWork):
    projects: ProjectRepository

    def __enter__(self) -> Self:
        super().__enter__()
        self.projects = SqlProjectRepository(self.session)
        return self
