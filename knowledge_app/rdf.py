"""Oracle native RDF patterns adapted from DB Companion, isolated namespace."""

import json
import re
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from knowledge_app.workflow import WorkflowInput

NETWORK = "VK_FLOW_RDF"
MODEL = "VK_FLOW"
VIEW = '"VK_FLOW_RDF#RDFT_VK_FLOW"'
P = "urn:vk:workflow:"


def graph(owner: str, revision: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{64}", owner):
        raise ValueError("Invalid owner")
    return f"urn:vk:workflow:{owner}:{UUID(revision)}"


def rows(owner: str, revision: str, workflow: WorkflowInput) -> list[tuple[str, str, str]]:
    base = graph(owner, revision)
    result = []
    for node in sorted(workflow.nodes, key=lambda n: n.id):
        result.append((f"<{base}/node/{node.id}>", f"<{P}label>", json.dumps(node.label, ensure_ascii=False)))
    for i, edge in enumerate(sorted(workflow.edges, key=lambda e: e.model_dump_json())):
        subject = f"<{base}/edge/{i}>"
        for key, value in edge.model_dump(exclude_none=True).items():
            obj = (
                f"<{base}/node/{value}>"
                if key in {"source", "target"}
                else json.dumps(value, ensure_ascii=False)
            )
            result.append((subject, f"<{P}{key}>", obj))
    return result


def insert(session: Session, owner: str, revision: str, workflow: WorkflowInput) -> None:
    session.execute(
        text(f"INSERT INTO {VIEW} (TRIPLE) VALUES (MDSYS.SDO_RDF_TRIPLE_S(:g,:s,:p,:o,USER,'{NETWORK}'))"),
        [
            {"g": f"{MODEL}:<{graph(owner, revision)}>", "s": s, "p": p, "o": o}
            for s, p, o in rows(owner, revision, workflow)
        ],
    )


def read(session: Session, owner: str, revision: str) -> WorkflowInput:
    # Accessors query native RDF directly, without requiring SEM_MATCH's DB JVM.
    result = session.execute(
        text(f"""SELECT
        t.TRIPLE.GET_SUBJECT(USER,'{NETWORK}'),
        t.TRIPLE.GET_PROPERTY(USER,'{NETWORK}'),
        t.TRIPLE.GET_OBJ_VALUE(USER,'{NETWORK}')
        FROM {VIEW} t
        WHERE t.TRIPLE.GET_MODEL(USER,'{NETWORK}') = :g
        FETCH FIRST 701 ROWS ONLY"""),
        {"g": f"{MODEL}:<{graph(owner, revision)}>"},
    ).all()
    if len(result) > 700:
        raise ValueError("RDF result limit")
    base = graph(owner, revision)
    nodes: dict[str, dict[str, str]] = {}
    edges: dict[str, dict[str, str]] = {}
    for subject, predicate, obj in result:
        subject, predicate, obj = str(subject), str(predicate), str(obj)
        if not predicate.startswith(f"<{P}") or not predicate.endswith(">"):
            raise ValueError("Invalid predicate")
        key = predicate[len(P) + 1 : -1]
        if subject.startswith(f"<{base}/node/") and key == "label":
            node_id = subject[len(base) + 7 : -1]
            nodes[node_id] = {"id": node_id, "label": json.loads(obj)}
        elif subject.startswith(f"<{base}/edge/"):
            if key in {"source", "target"}:
                if not obj.startswith(f"<{base}/node/") or not obj.endswith(">"):
                    raise ValueError("Invalid RDF node")
                value = obj[len(base) + 7 : -1]
            else:
                value = json.loads(obj)
            edges.setdefault(subject, {})[key] = value
        else:
            raise ValueError("Invalid RDF subject")
    return WorkflowInput.model_validate(
        {"verified": True, "nodes": list(nodes.values()), "edges": list(edges.values())}
    )
