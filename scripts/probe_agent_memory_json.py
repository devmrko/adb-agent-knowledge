"""Isolated SDK JSON/storage probe; synthetic vectors are not a quality benchmark."""

import argparse
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

from dotenv import dotenv_values
from sqlalchemy import text as sql_text

from knowledge_app.agent_memory_contracts import MemorySave
from knowledge_app.agent_memory_repository import SDKRepository
from knowledge_app.database import database
from knowledge_app.embedding import Piece
from knowledge_app.settings import Settings


class ProbeEmbedder:
    profile_id = "json-storage-probe-not-semantic"
    dimensions = 1024

    def __init__(self) -> None:
        self.inputs: list[str] = []

    def split(self, text: str) -> list[Piece]:
        return [Piece(text, 1, 0, len(text))]

    def encode(self, texts: list[str], *, query: bool = False) -> list[list[float]]:
        self.inputs.extend(texts)
        vectors = []
        for text in texts:
            digest = hashlib.sha256(text.encode()).digest()
            vectors.append([float(digest[i % 32] + 1) for i in range(self.dimensions)])
        return vectors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--store-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    values = {k.lower(): v for k, v in dotenv_values(args.env_file).items() if v is not None}
    if not values.get("user_name", "").startswith(("VKV_", "OAM_TEST_")):
        raise SystemExit("Requires isolated test account")
    if not re.fullmatch(r"JPROBE[0-9]{6,10}", args.store_id):
        raise SystemExit("Requires a JPROBE numeric test store ID")
    settings = Settings(_env_file=None, **values).model_copy(
        update={"agent_memory_store_id": args.store_id, "embedding_dimensions": 1024}
    )
    embedder = ProbeEmbedder()
    repo = SDKRepository(settings, embedder)
    results: dict[str, Any] = {
        "store_id": args.store_id,
        "vectors": "synthetic; no semantic quality claim",
        "cases": [],
    }
    prefix = str(time.time_ns())
    owner = "json-probe-" + prefix

    def check(name: str, fn: Any) -> Any:
        started = time.monotonic()
        try:
            detail = fn()
            results["cases"].append(
                {
                    "name": name,
                    "status": "PASS",
                    "seconds": round(time.monotonic() - started, 3),
                    "detail": detail,
                }
            )
            print(name, "PASS", flush=True)
            return detail
        except Exception as exc:
            results["cases"].append({"name": name, "status": "FAIL", "error_type": type(exc).__name__})
            print(name, "FAIL", type(exc).__name__, flush=True)
            return None
        finally:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2))

    try:
        repo.connect(initialize=True)
        store = repo.store
        for size in [1024, 32768, 262144, 1048576, 4194304]:

            def roundtrip(size: int = size) -> Any:
                record_id = f"{prefix}-{size}"
                body = {"schema_version": 1, "kind": "procedure", "detail": "가나다🙂" * (size // 13)}
                content = json.dumps(body, ensure_ascii=False)
                metadata = {
                    "project": "tasteby-demo",
                    "review": {"status": "draft"},
                    "tags": ["운영", "배포"],
                    "payload": body["detail"],
                }
                store.add(
                    contents=[content],
                    record_type="memory",
                    record_ids=record_id,
                    user_ids=owner,
                    metadata=metadata,
                    index_texts=["테스트 배포 절차"],
                )
                saved = store.get("memory", record_id)
                assert json.loads(saved.content) == body
                assert saved.metadata == metadata
                return {
                    "content_chars": len(content),
                    "content_utf8_bytes": len(content.encode()),
                    "metadata_utf8_bytes": len(json.dumps(metadata, ensure_ascii=False).encode()),
                }

            check(f"json_roundtrip_{size}", roundtrip)
        rid = f"{prefix}-filters"

        def filters() -> Any:
            metadata = {
                "project": "tasteby-demo",
                "review": {"status": "draft"},
                "tags": ["운영", "배포"],
                "untouched": True,
            }
            store.add(
                contents=['{"detail":"본문원본"}'],
                record_type="memory",
                record_ids=rid,
                user_ids=owner,
                metadata=metadata,
                index_texts=[["검색청크일", "검색청크이"]],
            )
            rows = store.list(
                "memory",
                user_id=owner,
                metadata_filter={"review": {"status": "draft"}, "tags": {"$array_contains": "배포"}},
                limit=100,
            )
            assert rid in [r.id for r in rows]
            assert not store.list(
                "memory", user_id=owner, metadata_filter={"review": {"status": "approved"}}, limit=100
            )
            assert not store.list("memory", user_id="another-owner", limit=100)
            search = store.search(
                "배포",
                k=100,
                user_id=owner,
                exact_user_match=True,
                metadata_filter={"untouched": True},
                record_types={"memory"},
            )
            assert rid in [r.id for r, _ in search]
            assert "검색청크일" in embedder.inputs and "검색청크이" in embedder.inputs
            assert '{"detail":"본문원본"}' not in embedder.inputs
            return (
                "nested/array predicates, owner isolation, separate index chunks and filtered vector search"
            )

        check("filters_and_index_text", filters)

        def update() -> Any:
            before = len(embedder.inputs)
            store.update("memory", rid, metadata={"review": {"status": "approved"}})
            row = store.get("memory", rid)
            assert row.metadata == {"review": {"status": "approved"}}
            assert len(embedder.inputs) == before
            store.update("memory", rid, content='{"detail":"수정본문"}', index_text="새검색청크")
            row = store.get("memory", rid)
            assert row.content == '{"detail":"수정본문"}'
            assert "새검색청크" in embedder.inputs[before:]
            return (
                "metadata replaces object (no deep merge/no embedding); content+index update invokes embedder"
            )

        check("update_semantics", update)

        def mapping() -> Any:
            value = {"summary": "한글", "detail": {"steps": ["확인", "배포"]}}
            mrid = f"{prefix}-mapping"
            store.add(
                contents=[value],
                record_type="memory",
                record_ids=mrid,
                user_ids=owner,
                index_texts=["중첩 JSON"],
            )
            content = store.get("memory", mrid).content
            assert json.loads(content) == value
            return {"returned_type": type(content).__name__, "json_roundtrip": True}

        check("mapping_content_support", mapping)

        def persisted_index() -> Any:
            engine = database(settings)
            try:
                with engine.connect() as connection:
                    rows = connection.execute(
                        sql_text(
                            f"SELECT chunk_text, embedding FROM {args.store_id}_RECORD_CHUNKS WHERE user_id=:owner AND source_id=:id"
                        ),
                        {"owner": owner, "id": rid},
                    ).all()
                    assert len(rows) == 1
                    chunk = rows[0][0]
                    if hasattr(chunk, "read"):
                        chunk = chunk.read()
                    assert chunk == "새검색청크"
                    assert list(rows[0][1]) == embedder.encode(["새검색청크"])[0]
                    count = connection.execute(
                        sql_text(
                            f"SELECT COUNT(*) FROM {args.store_id}_MEMORY WHERE user_id=:owner AND record_id=:id AND JSON_VALUE(metadata, '$.review.status')='approved'"
                        ),
                        {"owner": owner, "id": rid},
                    ).scalar_one()
                    assert count == 1
                return "stored chunk replaced, vector equals updated input encoding, nested JSON SQL predicate matches"
            finally:
                engine.dispose()

        check("persisted_index_and_json_sql", persisted_index)

        def app_limits() -> Any:
            MemorySave(title="시험", text="가" * 12000, idempotency_key="test")
            try:
                MemorySave(title="시험", text="가" * 12001, idempotency_key="test")
            except ValueError:
                return "current MCP DTO permits 12000 characters; rejects 12001"
            raise AssertionError("Expected size rejection")

        check("current_app_limit", app_limits)
    finally:
        repo.close()


if __name__ == "__main__":
    main()
