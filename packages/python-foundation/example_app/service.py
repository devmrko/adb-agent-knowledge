"""Shared service for API, HTML and workers; functional permissions apply to direct calls too."""

from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from example_app.models import (
    INVALID_PAGE,
    NOT_FOUND,
    VERSION_CONFLICT,
    CreateProject,
    Project,
    ProjectListing,
    ProjectView,
    RenameProject,
)
from example_app.repository import ProjectRepository, ProjectUnitOfWork
from python_foundation.errors import BusinessError
from python_foundation.security import Actor


class ProjectService:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def create(self, command: CreateProject, actor: Actor) -> ProjectView:
        self._write_authority(actor)
        with ProjectUnitOfWork(self._factory) as uow:
            return ProjectView.model_validate(uow.projects.create(command.name))

    def get(self, project_id: str, actor: Actor) -> ProjectView:
        with ProjectUnitOfWork(self._factory, read_only=True) as uow:
            return ProjectView.model_validate(self._required(uow.projects, project_id))

    def list(self, page: int, actor: Actor) -> ProjectListing:
        if not 0 <= page <= 100000:
            raise BusinessError(INVALID_PAGE)
        with ProjectUnitOfWork(self._factory, read_only=True) as uow:
            return ProjectListing(
                items=[ProjectView.model_validate(item) for item in uow.projects.list(page, 20)],
                page=page,
                size=20,
                total=uow.projects.count(),
            )

    def update(self, project_id: str, command: RenameProject, actor: Actor) -> ProjectView:
        self._write_authority(actor)
        try:
            with ProjectUnitOfWork(self._factory) as uow:
                project = self._required(uow.projects, project_id)
                if project.version != command.version:
                    raise BusinessError(VERSION_CONFLICT)
                project.name = command.name
                uow.projects.flush()
                return ProjectView.model_validate(project)
        except StaleDataError as failure:
            raise BusinessError(VERSION_CONFLICT) from failure

    def delete(self, project_id: str, actor: Actor) -> None:
        self._write_authority(actor)
        try:
            with ProjectUnitOfWork(self._factory) as uow:
                uow.projects.delete(self._required(uow.projects, project_id))
        except StaleDataError as failure:
            raise BusinessError(VERSION_CONFLICT) from failure

    @staticmethod
    def _required(repository: ProjectRepository, project_id: str) -> Project:
        project = repository.find(project_id)
        if project is None:
            raise BusinessError(NOT_FOUND)
        return project

    @staticmethod
    def _write_authority(actor: Actor) -> None:
        # Explicit demo policy: local USER or validated access-token project:write scope.
        # This shared workspace has no tenant or ownership model.
        if "ROLE_USER" not in actor.authorities:
            actor.require("SCOPE_project:write")
