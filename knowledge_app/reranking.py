"""Lazy, pinned cross-encoder. Scores are sigmoid outputs, not probabilities."""

import math
import re
import threading
from typing import Any, Protocol

from knowledge_app.settings import Settings


class Reranker(Protocol):
    def score(self, query: str, passages: list[str]) -> list[float]: ...


def validate_scores(scores: list[float], count: int) -> None:
    if len(scores) != count or any(not math.isfinite(v) or not 0 <= v <= 1 for v in scores):
        raise ValueError("Invalid reranker scores")


class CrossEncoderReranker:
    def __init__(self, settings: Settings) -> None:
        if not re.fullmatch(r"[0-9a-f]{40}", settings.reranker_revision):
            raise ValueError("Pin RERANKER_REVISION to a Hugging Face commit")
        self.settings = settings
        self._model: Any = None
        self._lock = threading.RLock()

    def score(self, query: str, passages: list[str]) -> list[float]:
        if not passages:
            return []
        with self._lock:
            import torch
            from sentence_transformers import CrossEncoder

            if self._model is None:
                self._model = CrossEncoder(
                    self.settings.reranker_model,
                    revision=self.settings.reranker_revision,
                    device=self.settings.reranker_device,
                    max_length=self.settings.reranker_max_length,
                    trust_remote_code=False,
                    activation_fn=torch.nn.Sigmoid(),
                )
            scores: list[float] = (
                self._model.predict(
                    [(query, passage) for passage in passages],
                    batch_size=self.settings.reranker_batch_size,
                    show_progress_bar=False,
                    convert_to_numpy=True,
                )
                .reshape(-1)
                .tolist()
            )
            validate_scores(scores, len(passages))
            return scores
