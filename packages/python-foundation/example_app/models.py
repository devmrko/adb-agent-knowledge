"""Application entity and typed API contracts."""

import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from python_foundation.errors import ErrorCategory, ErrorSpec


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False, default=0)
    __mapper_args__ = {
        "version_id_col": version,
        "version_id_generator": lambda value: 0 if value is None else value + 1,
    }


class CreateProject(BaseModel):
    name: str = Field(min_length=1, max_length=160)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name must not be blank")
        return value


class RenameProject(CreateProject):
    version: int = Field(ge=0)


class ProjectView(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)
    id: str
    name: str
    version: int


class ProjectListing(BaseModel):
    items: list[ProjectView]
    page: int
    size: int
    total: int


NOT_FOUND = ErrorSpec("PROJECT_NOT_FOUND", ErrorCategory.NOT_FOUND, "Project not found.")
VERSION_CONFLICT = ErrorSpec(
    "PROJECT_VERSION_CONFLICT", ErrorCategory.CONFLICT, "Project was modified. Reload and retry."
)
INVALID_PAGE = ErrorSpec("INVALID_PAGE", ErrorCategory.VALIDATION, "Invalid page.")
