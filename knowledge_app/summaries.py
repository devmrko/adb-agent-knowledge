"""Bounded revision summaries; extractive fallback never invents facts."""

import re
from typing import Any

from knowledge_app.models import Revision


def extract_summary(text: str, limit: int = 800) -> str:
    parts = [p.strip() for p in re.split(r"(?<=[.!?。])\s+|\n+", text) if p.strip()]
    return "\n".join(parts[:4])[:limit].rstrip()


def summary_view(revision: Revision) -> dict[str, Any]:
    return {
        "summary": revision.summary_text or extract_summary(revision.content_text or ""),
        "summary_kind": revision.summary_kind or "EXTRACTIVE",
        "summary_persisted": bool(revision.summary_text),
        "summary_revision_id": revision.id,
    }
