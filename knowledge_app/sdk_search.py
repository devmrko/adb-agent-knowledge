"""Search SDK-managed chunks while retaining canonical source IDs and locators."""

import re
from typing import Any

from sqlalchemy import Integer, String, Text, column, select, table
from sqlalchemy.orm import aliased

from knowledge_app.models import Chunk, SourceTransfer, Vector


def sdk_chunks(store_id: str) -> Any:
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,15}", store_id):
        raise ValueError("Invalid SDK store identifier")
    return table(
        store_id + "_RECORD_CHUNKS",
        column("source_id", String(64)),
        column("source_record_type", String(32)),
        column("user_id", String(64)),
        column("chunk_seq", Integer()),
        column("chunk_text", Text()),
        column("embedding", Vector()),
    )


def sdk_chunk_model(store_id: str) -> Any:
    sdk = sdk_chunks(store_id)
    # SDK chunk_seq starts at 1; the application's stable locator chunk_no starts at 0.
    projection = (
        select(
            Chunk.id,
            Chunk.owner_id,
            Chunk.revision_id,
            Chunk.source_part,
            Chunk.chunk_no,
            sdk.c.chunk_text.label("text"),
            Chunk.page_no,
            Chunk.char_start,
            Chunk.char_end,
            Chunk.profile_id,
            sdk.c.embedding.label("embedding"),
        )
        .join(
            SourceTransfer,
            (SourceTransfer.owner_id == Chunk.owner_id) & (SourceTransfer.revision_id == Chunk.revision_id),
        )
        .join(
            sdk,
            (sdk.c.source_id == SourceTransfer.sdk_record_id)
            & (sdk.c.user_id == Chunk.owner_id)
            & (sdk.c.source_record_type == "memory")
            & (sdk.c.chunk_seq == Chunk.chunk_no + 1),
        )
        .where(
            SourceTransfer.status == "ACTIVE",
            SourceTransfer.store_id == store_id,
            SourceTransfer.profile_id == Chunk.profile_id,
        )
        .subquery("sdk_source_chunks")
    )
    return aliased(Chunk, projection, adapt_on_names=True)
