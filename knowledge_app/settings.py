from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore", populate_by_name=True)
    api_host: str = "127.0.0.1"
    ui_auto_connect: bool = True
    web_public_origin: str = ""
    web_api_key_sha256: str = ""
    web_actor_issuer: str = "local-development"
    web_actor_subject: str = "developer"
    web_session_db: str = str(ROOT / ".run" / "browser-sessions.db")
    web_session_ttl_seconds: int = Field(default=604800, ge=60, le=2592000)
    workflow_rdf_enabled: bool = False
    property_graph_enabled: bool = False
    api_port: int = Field(default=8000, ge=1, le=65535)
    environment: Literal["development", "production"] = "development"
    database_url: str = "oracle+oracledb://"
    user_name: str = ""
    user_password: SecretStr = SecretStr("")
    wallet_password: SecretStr | None = None
    wallet_dir: str = ""
    oracle_dsn: str = ""
    dev_api_token: SecretStr | None = None
    issuer: str = "https://identity.example.invalid"
    audience: str = "knowledge-api"
    jwks_url: str = "https://identity.example.invalid/keys"
    embedding_provider: Literal["local", "openai"] = "local"
    embedding_url: str = ""
    embedding_api_key: SecretStr = SecretStr("")
    embedding_timeout_seconds: float = Field(default=30, ge=1, le=120)
    embedding_query_prefix: str = ""
    embedding_chunk_chars: int = Field(default=512, ge=64, le=4096)
    embedding_overlap_chars: int = Field(default=64, ge=0, le=512)
    embedding_model: str = "dragonkue/snowflake-arctic-embed-l-v2.0-ko"
    embedding_revision: str = "main"
    embedding_device: Literal["cpu", "mps", "cuda"] = "cpu"
    embedding_dimensions: int = Field(default=1024, ge=1024, le=1024)
    embedding_batch_size: int = Field(default=4, ge=1, le=128)
    chunk_tokens: int = Field(default=384, ge=32, le=1024)
    chunk_overlap: int = Field(default=48, ge=0, le=128)
    url_allowed_hosts: str = ""
    max_source_bytes: int = 10_000_000
    max_pptx_source_bytes: int = Field(default=100_000_000, ge=1, le=100_000_000)
    max_text_chars: int = 200_000
    search_min_similarity: float = Field(default=0.28, ge=0, le=1)
    reranker_enabled: bool = False
    reranker_model: str = "dragonkue/bge-reranker-v2-m3-ko"
    reranker_revision: str = "2aca5884ecac490192af9ebd86836d9073d826cd"
    reranker_device: Literal["cpu", "mps", "cuda"] = "cpu"
    reranker_batch_size: int = Field(default=4, ge=1, le=32)
    reranker_max_length: int = Field(default=512, ge=64, le=8192)
    reranker_candidates: int = Field(default=20, ge=20, le=100)
    reranker_min_score: float = Field(default=0.5, ge=0, le=1)
