"""Public contracts for the optional Oracle agent memory adapter."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MemoryQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    query: str = Field(default="", max_length=2000)
    agent_id: str | None = Field(default=None, max_length=128)
    thread_id: str | None = Field(default=None, max_length=128)
    scope: str | None = Field(default=None, max_length=108)
    offset: int = Field(default=0, ge=0, le=900)
    limit: int = Field(default=10, ge=1, le=50)
    include_invalid: bool = False
    include_connections: bool = False


class MemorySave(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=12000)
    memory_type: Literal["memory", "fact", "preference", "guideline"] = "memory"
    scope: str = Field(default="global", min_length=1, max_length=108)
    agent_id: str | None = Field(default=None, max_length=128)
    origin_thread_id: str | None = Field(default=None, max_length=128)
    idempotency_key: str = Field(min_length=1, max_length=100)


class ProfileSave(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    kind: Literal["user", "agent", "thread"]
    key: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    agent_id: str | None = Field(default=None, max_length=128)
    scope: str = Field(default="global", min_length=1, max_length=108)
    expected_version: int = Field(default=0, ge=0)


class MemoryRename(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    memory_id: str = Field(min_length=1, max_length=128)
    expected_title: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=500)
