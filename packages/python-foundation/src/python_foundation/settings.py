"""Validated settings; applications may subclass instead of wrapping every field."""

from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class FoundationSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FOUNDATION_", extra="ignore")

    environment: Literal["development", "production"] = "development"
    database_url: SecretStr = SecretStr("sqlite:///foundation.db")
    pool_size: int = Field(default=2, ge=1, le=100)
    pool_timeout: float = Field(default=5.0, gt=0)
    sqlite_busy_timeout_ms: int = Field(default=5000, ge=1)
    auth_mode: Literal["session", "token", "mixed"] = "session"
    cookie_secure: bool = False
    session_ttl_seconds: int = Field(default=1800, ge=60, le=86400)
    issuer: str | None = None
    audience: str | None = None
    jwks_url: str | None = None
    http_timeout_seconds: float = Field(default=5.0, gt=0)
    http_max_connections: int = Field(default=20, ge=1)
    max_request_bytes: int = Field(default=1_048_576, ge=1024)
    development_password: SecretStr | None = None

    @model_validator(mode="after")
    def validate_boundaries(self) -> Self:
        from sqlalchemy.engine import make_url

        url = make_url(self.database_url.get_secret_value())
        if url.drivername not in {"sqlite", "sqlite+pysqlite", "oracle+oracledb"}:
            raise ValueError("Use sqlite or oracle+oracledb with the synchronous SQLAlchemy adapter")
        if self.environment == "production" and self.auth_mode != "token" and not self.cookie_secure:
            raise ValueError("Production session cookies require cookie_secure=true")
        if self.auth_mode in {"token", "mixed"}:
            if not self.audience or not self.audience.strip():
                raise ValueError("Token authentication requires an API audience")
            for value in (self.issuer, self.jwks_url):
                parsed = urlsplit(value or "")
                if (
                    parsed.scheme != "https"
                    or not parsed.hostname
                    or parsed.username
                    or parsed.password
                    or parsed.fragment
                    or parsed.query
                ):
                    raise ValueError(
                        "Token authentication requires HTTPS issuer and JWKS URLs without credentials/query/fragment"
                    )
        return self
