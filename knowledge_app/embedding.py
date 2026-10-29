import hashlib
import json
import math
import re
import threading
from dataclasses import dataclass
from typing import Any, Protocol

from knowledge_app.extraction import NOTES_MARKER
from knowledge_app.settings import Settings


@dataclass
class Piece:
    text: str
    page: int
    start: int
    end: int
    source_part: str | None = None


class Embedder(Protocol):
    profile_id: str
    dimensions: int

    def split(self, text: str) -> list[Piece]: ...
    def encode(self, texts: list[str], *, query: bool = False) -> list[list[float]]: ...


def validate_vectors(vectors: list[list[float]], count: int, dimensions: int) -> None:
    if len(vectors) != count or any(
        len(v) != dimensions or not all(math.isfinite(x) for x in v) or not any(v) for v in vectors
    ):
        raise ValueError("Invalid embedding shape or values")


class SentenceEmbedder:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.dimensions: int = settings.embedding_dimensions
        self._model: Any = None
        self._lock = threading.RLock()
        if settings.chunk_overlap >= settings.chunk_tokens:
            raise ValueError("Overlap must be smaller than chunk size")
        if not re.fullmatch(r"[0-9a-f]{40}", settings.embedding_revision):
            raise ValueError("Pin EMBEDDING_REVISION to a Hugging Face commit before ingestion")
        self.profile_id = hashlib.sha256(
            json.dumps(
                [
                    settings.embedding_model,
                    settings.embedding_revision,
                    self.dimensions,
                    settings.chunk_tokens,
                    settings.chunk_overlap,
                    "query-prompt-v1",
                ]
            ).encode()
        ).hexdigest()

    def model(self) -> Any:
        with self._lock:
            if self._model is None:
                from sentence_transformers import SentenceTransformer

                candidate = SentenceTransformer(
                    self.settings.embedding_model,
                    revision=self.settings.embedding_revision,
                    device=self.settings.embedding_device,
                    trust_remote_code=False,
                )
                if candidate.get_sentence_embedding_dimension() != self.dimensions:
                    raise ValueError("Model dimension mismatch")
                if self.settings.chunk_tokens + 16 > candidate.max_seq_length:
                    raise ValueError("Chunk token budget exceeds model input capacity")
                if self.settings.embedding_device == "cuda":
                    candidate.bfloat16()
                self._model = candidate
            return self._model

    def split(self, text: str) -> list[Piece]:
        model = self.model()
        result: list[Piece] = []
        base = 0
        for page, value in enumerate(text.split("\f"), 1):
            sections = value.split(NOTES_MARKER, 1)
            section_base = base
            for section_no, section_text in enumerate(sections):
                offsets = model.tokenizer(
                    section_text, add_special_tokens=False, truncation=False, return_offsets_mapping=True
                )["offset_mapping"]
                step = self.settings.chunk_tokens - self.settings.chunk_overlap
                for i in range(0, len(offsets), step):
                    section = offsets[i : i + self.settings.chunk_tokens]
                    start, end = int(section[0][0]), int(section[-1][1])
                    if section_text[start:end].strip():
                        result.append(
                            Piece(
                                section_text[start:end],
                                page,
                                section_base + start,
                                section_base + end,
                                "notes" if section_no else "body",
                            )
                        )
                    if i + self.settings.chunk_tokens >= len(offsets):
                        break
                section_base += len(section_text) + len(NOTES_MARKER)
            base += len(value) + 1
        return result

    def encode(self, texts: list[str], *, query: bool = False) -> list[list[float]]:
        with self._lock:
            model = self.model()
            options: dict[str, Any] = {}
            if query:
                options["prompt_name"] = "query"
            vectors: list[list[float]] = model.encode(
                texts,
                normalize_embeddings=True,
                batch_size=self.settings.embedding_batch_size,
                show_progress_bar=False,
                **options,
            ).tolist()
            validate_vectors(vectors, len(texts), self.dimensions)
            return vectors


class RemoteEmbedder:
    """OpenAI-compatible vectors; no local model download or inference."""

    def __init__(self, settings: Settings, *, transport: Any = None) -> None:
        from knowledge_app.provider_http import endpoint

        self.settings, self.transport = settings, transport
        self.url = endpoint(settings.embedding_url)
        self.dimensions = settings.embedding_dimensions
        if settings.embedding_revision in {"", "main", "latest"}:
            raise ValueError("Pin the remote embedding model revision")
        if settings.embedding_overlap_chars >= settings.embedding_chunk_chars:
            raise ValueError("Character overlap must be smaller than chunk size")
        self.profile_id = hashlib.sha256(
            json.dumps(
                [
                    "openai-char-v1",
                    settings.embedding_model,
                    settings.embedding_revision,
                    self.dimensions,
                    settings.embedding_chunk_chars,
                    settings.embedding_overlap_chars,
                    settings.embedding_query_prefix,
                ]
            ).encode()
        ).hexdigest()

    def split(self, text: str) -> list[Piece]:
        result: list[Piece] = []
        base = 0
        size = self.settings.embedding_chunk_chars
        step = size - self.settings.embedding_overlap_chars
        for page, value in enumerate(text.split("\f"), 1):
            section_base = base
            for number, section in enumerate(value.split(NOTES_MARKER, 1)):
                for start in range(0, len(section), step):
                    end = min(start + size, len(section))
                    if section[start:end].strip():
                        result.append(
                            Piece(
                                section[start:end],
                                page,
                                section_base + start,
                                section_base + end,
                                "notes" if number else "body",
                            )
                        )
                    if end == len(section):
                        break
                section_base += len(section) + len(NOTES_MARKER)
            base += len(value) + 1
        return result

    def encode(self, texts: list[str], *, query: bool = False) -> list[list[float]]:
        import httpx

        if not texts:
            return []
        key = self.settings.embedding_api_key.get_secret_value()
        headers = {"Authorization": "Bearer " + key} if key else {}
        vectors: list[list[float]] = []
        try:
            with httpx.Client(
                timeout=self.settings.embedding_timeout_seconds,
                trust_env=False,
                follow_redirects=False,
                transport=self.transport,
            ) as client:
                size = self.settings.embedding_batch_size
                for offset in range(0, len(texts), size):
                    batch = texts[offset : offset + size]
                    inputs = [self.settings.embedding_query_prefix + t for t in batch] if query else batch
                    response = client.post(
                        self.url + "/embeddings",
                        headers=headers,
                        json={
                            "model": self.settings.embedding_model,
                            "input": inputs,
                            "encoding_format": "float",
                        },
                    )
                    response.raise_for_status()
                    data = response.json()["data"]
                    if len(data) != len(batch) or sorted(row["index"] for row in data) != list(
                        range(len(batch))
                    ):
                        raise ValueError("Invalid response indexes")
                    ordered = sorted(data, key=lambda row: row["index"])
                    values = [row["embedding"] for row in ordered]
                    if any(isinstance(x, bool) or not isinstance(x, (float, int)) for v in values for x in v):
                        raise ValueError("Invalid numeric values")
                    validate_vectors(values, len(batch), self.dimensions)
                    for v in values:
                        norm = math.hypot(*v)
                        if not math.isfinite(norm):
                            raise ValueError("Invalid norm")
                        vectors.append([x / norm for x in v])
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
            raise ValueError("Remote embedding failed; check provider availability and profile") from None
        return vectors


def create_embedder(settings: Settings) -> Embedder:
    return RemoteEmbedder(settings) if settings.embedding_provider == "openai" else SentenceEmbedder(settings)
