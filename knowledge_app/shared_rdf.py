"""Shared entities with assertion-version provenance in native Oracle RDF."""

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from knowledge_app.rdf import NETWORK, graph

MODEL = "VK_SHARED"
VIEW = '"VK_FLOW_RDF#RDFT_VK_SHARED"'
READ_VIEW = '"VK_FLOW_RDF#RDFM_VK_SHARED"'
VALUE_VIEW = '"VK_FLOW_RDF#RDF_VALUE$"'
P = "urn:vk:shared:"

# Resolve a bound graph URI against stored dictionary keys, then filter native
# triples by G_ID, instead of using GET_MODEL as the per-row filter.
# Numeric construction only represents existing IDs; it does not insert data.
READ_GRAPH_SQL = f"""
SELECT t.TRIPLE.GET_SUBJECT(USER,'{NETWORK}'),
       t.TRIPLE.GET_PROPERTY(USER,'{NETWORK}'),
       t.TRIPLE.GET_OBJ_VALUE(USER,'{NETWORK}')
FROM (
    SELECT MDSYS.SDO_RDF_TRIPLE_S(
        r.CANON_END_NODE_ID, r.MODEL_ID, r.START_NODE_ID,
        r.P_VALUE_ID, r.END_NODE_ID
    ) AS TRIPLE
    FROM {READ_VIEW} r
    WHERE r.G_ID IN (
        SELECT v.VALUE_ID FROM {VALUE_VIEW} v
        WHERE v.VALUE_TYPE = 'UR'
          AND (v.VNAME_PREFIX = SEM_APIS.VALUE_NAME_PREFIX(:graph_uri, 'UR')
               OR (v.VNAME_PREFIX IS NULL
                   AND SEM_APIS.VALUE_NAME_PREFIX(:graph_uri, 'UR') IS NULL))
          AND (v.VNAME_SUFFIX = SEM_APIS.VALUE_NAME_SUFFIX(:graph_uri, 'UR')
               OR (v.VNAME_SUFFIX IS NULL
                   AND SEM_APIS.VALUE_NAME_SUFFIX(:graph_uri, 'UR') IS NULL))
    )
) t
FETCH FIRST 301 ROWS ONLY
"""


def stamp(value: datetime) -> str:
    return (
        value.replace(tzinfo=UTC).isoformat() if value.tzinfo is None else value.astimezone(UTC).isoformat()
    )


def rows(
    version: str,
    claim: str,
    payload: dict[str, Any],
    recorded_from: datetime,
    recorded_to: datetime | None = None,
) -> list[tuple[str, str, str]]:
    subject = f"<urn:vk:assertion:{UUID(version)}>"
    result = [(subject, f"<{P}claim>", f"<urn:vk:claim:{UUID(claim)}>")]

    def add(s: str, predicate: str, value: str, iri: bool = False) -> None:
        result.append(
            (s, f"<{P}{predicate}>", f"<{value}>" if iri else json.dumps(value, ensure_ascii=False))
        )

    for key, value in payload.items():
        if key == "evidence":
            for i, evidence in enumerate(value):
                node = f"<urn:vk:assertion:{version}/evidence/{i}>"
                add(subject, "evidence", node[1:-1], True)
                for k, v in evidence.items():
                    add(node, k, str(v))
        elif value is not None:
            if key in {"subject_id", "object_id"}:
                add(subject, key, "urn:vk:entity:" + str(UUID(str(value))), True)
            else:
                add(
                    subject,
                    key,
                    json.dumps(value, ensure_ascii=False, sort_keys=True)
                    if isinstance(value, (dict, list, bool))
                    else str(value),
                )
    add(subject, "recorded_from", stamp(recorded_from))
    if recorded_to:
        add(subject, "recorded_to", stamp(recorded_to))
    return result


def insert(
    session: Session, owner: str, version: str, claim: str, payload: dict[str, Any], recorded: datetime
) -> None:
    insert_rows(session, owner, version, rows(version, claim, payload, recorded))


def insert_rows(session: Session, owner: str, version: str, values: list[tuple[str, str, str]]) -> None:
    session.execute(
        text(f"INSERT INTO {VIEW} (TRIPLE) VALUES (MDSYS.SDO_RDF_TRIPLE_S(:g,:s,:p,:o,USER,'{NETWORK}'))"),
        [{"g": f"{MODEL}:<{graph(owner, version)}>", "s": s, "p": p, "o": o} for s, p, o in values],
    )


def close(session: Session, owner: str, version: str, recorded: datetime) -> None:
    insert_rows(
        session,
        owner,
        version,
        [(f"<urn:vk:assertion:{UUID(version)}>", f"<{P}recorded_to>", json.dumps(stamp(recorded)))],
    )


def verify(
    session: Session,
    owner: str,
    version: str,
    claim: str,
    payload: dict[str, Any],
    start: datetime,
    end: datetime | None,
) -> None:
    try:
        found = session.execute(
            text(READ_GRAPH_SQL),
            {"graph_uri": graph(owner, version)},
        ).all()
    except SQLAlchemyError as exc:
        code = re.search(r"ORA-\d{5}", str(exc.orig)) if hasattr(exc, "orig") else None
        logging.getLogger("python_foundation.graph").error(
            "rdf_graph_read_failed code=%s", code.group(0) if code else "UNKNOWN"
        )
        raise

    def normalize(row: Any) -> tuple[str, str, str]:
        s, p, o = (str(v) for v in row)
        # Oracle GET_OBJ_VALUE returns outer quotes with an already unescaped body.
        return s, p, json.dumps(o[1:-1], ensure_ascii=False) if o.startswith('"') and o.endswith('"') else o

    if len(found) > 300 or {normalize(row) for row in found} != set(
        rows(version, claim, payload, start, end)
    ):
        logging.getLogger("python_foundation.graph").error("rdf_graph_mismatch rows=%d", len(found))
        raise ValueError("Native RDF assertion mismatch")
