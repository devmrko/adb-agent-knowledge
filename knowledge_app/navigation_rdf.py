"""Structural references, distinct from evidence-backed business assertions."""

import hashlib
import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from knowledge_app.models import NavigationSnapshot, Revision
from knowledge_app.rdf import NETWORK, graph

MODEL = "VK_NAV"
VIEW = '"VK_FLOW_RDF#RDFT_VK_NAV"'
P = "urn:vk:navigation:"


def node(kind: str, identity: str) -> str:
    key = (
        str(UUID(identity))
        if kind in {"index", "knowledge", "revision", "entry"}
        else hashlib.sha256(identity.encode()).hexdigest()
    )
    return f"<urn:vk:{kind}:{key}>"


def edge(source: str, predicate: str, target: str) -> tuple[str, str, str]:
    return source, f"<{P}{predicate}>", target


def revision_rows(revision: Revision, scope: str, memory_kind: str) -> list[tuple[str, str, str]]:
    source = node("revision", revision.id)
    knowledge = node("knowledge", revision.item_id)
    rows = [
        edge(source, "revision_of", knowledge),
        edge(knowledge, "in_scope", node("scope", scope)),
        edge(knowledge, "memory_kind", json.dumps(memory_kind)),
    ]
    for reference in json.loads(revision.sources_json or "[]"):
        identity = json.dumps(reference, sort_keys=True, ensure_ascii=False)
        ref = node("source", identity)
        rows.append(edge(source, "has_source", ref))
        if reference.get("machine_id"):
            rows.append(edge(ref, "on_machine", node("machine", reference["machine_id"])))
    if revision.original_data is not None:
        rows.append(edge(source, "has_original", node("original", revision.id)))
    if revision.origin_machine_id:
        rows.append(edge(source, "written_on", node("machine", revision.origin_machine_id)))
    return rows


def store(
    session: Session, owner: str, snapshot_id: str, rows: list[tuple[str, str, str]], enabled: bool
) -> None:
    payload = json.dumps(sorted(set(rows)), ensure_ascii=False)
    snapshot = session.get(NavigationSnapshot, snapshot_id)
    if snapshot and (snapshot.owner_id != owner or snapshot.payload_json != payload):
        raise ValueError("Navigation snapshot conflict")
    if snapshot is None:
        snapshot = NavigationSnapshot(id=snapshot_id, owner_id=owner, payload_json=payload, native_stored=0)
        session.add(snapshot)
    if enabled and session.get_bind().dialect.name == "oracle" and not snapshot.native_stored:
        session.execute(
            text(
                f"INSERT INTO {VIEW} (TRIPLE) VALUES (MDSYS.SDO_RDF_TRIPLE_S(:g,:s,:p,:o,USER,'{NETWORK}'))"
            ),
            [
                {"g": f"{MODEL}:<{graph(owner, snapshot_id)}>", "s": s, "p": p, "o": o}
                for s, p, o in sorted(set(rows))
            ],
        )
        snapshot.native_stored = 1
    session.flush()
    read(session, owner, snapshot_id)


def read(session: Session, owner: str, snapshot_id: str) -> dict[str, Any]:
    snapshot = session.get(NavigationSnapshot, snapshot_id)
    if snapshot is None or snapshot.owner_id != owner:
        return {"status": "NOT_INDEXED", "edges": []}
    expected = json.loads(snapshot.payload_json)
    if snapshot.native_stored:
        found = session.execute(
            text(
                f"SELECT t.TRIPLE.GET_SUBJECT(USER,'{NETWORK}'), t.TRIPLE.GET_PROPERTY(USER,'{NETWORK}'), t.TRIPLE.GET_OBJ_VALUE(USER,'{NETWORK}') FROM {VIEW} t WHERE t.TRIPLE.GET_MODEL(USER,'{NETWORK}')=:g FETCH FIRST 1001 ROWS ONLY"
            ),
            {"g": f"{MODEL}:<{graph(owner, snapshot_id)}>"},
        ).all()
        normalized = []
        for s, p, o in found:
            o = str(o)
            normalized.append(
                [
                    str(s),
                    str(p),
                    json.dumps(o[1:-1], ensure_ascii=False) if o.startswith('"') and o.endswith('"') else o,
                ]
            )
        if sorted(normalized) != sorted(expected):
            raise ValueError("Navigation RDF mismatch")
    return {
        "status": "READY",
        "storage": "oracle_rdf" if snapshot.native_stored else "relational_metadata",
        "edges": [
            {"source": s, "relation": p[1:-1].removeprefix(P), "target": o, "kind": "structural_reference"}
            for s, p, o in expected
        ],
    }
