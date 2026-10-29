"""Inspect or explicitly install a read-only SQL Property Graph over canonical graph rows."""

import argparse

from sqlalchemy import text

from knowledge_app.database import database
from knowledge_app.settings import Settings

DDL = (
    """CREATE OR REPLACE VIEW VK_KG_ENTITIES AS
       SELECT id, owner_id, scope, identity_key, label, kind FROM vk_g_entity""",
    """CREATE OR REPLACE VIEW VK_KG_RELATIONS AS
       SELECT v.id, v.owner_id, v.scope, v.subject_id, v.object_id, v.claim_id,
              v.predicate, v.status, v.temporal_kind, v.valid_from, v.valid_to,
              v.recorded_from, v.recorded_to
       FROM vk_g_version v
       JOIN vk_g_entity s ON s.id=v.subject_id AND s.owner_id=v.owner_id
       JOIN vk_g_entity t ON t.id=v.object_id AND t.owner_id=v.owner_id
       WHERE v.object_id IS NOT NULL""",
    """CREATE OR REPLACE PROPERTY GRAPH VK_KNOWLEDGE_GRAPH
       VERTEX TABLES (VK_KG_ENTITIES AS entities KEY (id)
          LABEL entity PROPERTIES (id, owner_id, scope, identity_key, label, kind))
       EDGE TABLES (VK_KG_RELATIONS AS relations KEY (id)
          SOURCE KEY (subject_id) REFERENCES entities (id)
          DESTINATION KEY (object_id) REFERENCES entities (id)
          LABEL relation PROPERTIES (id, owner_id, scope, claim_id, predicate, status,
             temporal_kind, valid_from, valid_to, recorded_from, recorded_to))
       OPTIONS (TRUSTED MODE)""",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    engine = database(Settings())
    try:
        if engine.dialect.name != "oracle":
            raise SystemExit("Oracle required")
        with engine.connect() as connection:
            print(
                "Oracle version:",
                connection.scalar(
                    text(
                        "SELECT version FROM product_component_version WHERE product LIKE 'Oracle%' FETCH FIRST 1 ROW ONLY"
                    )
                ),
            )
            privilege = connection.scalar(
                text(
                    "SELECT COUNT(*) FROM SESSION_PRIVS WHERE PRIVILEGE IN ('CREATE PROPERTY GRAPH', 'CREATE ANY PROPERTY GRAPH')"
                )
            )
            print("Property graph creation privilege:", bool(privilege))
            existing = connection.execute(
                text(
                    "SELECT object_name, object_type, status FROM user_objects WHERE object_name IN ('VK_KG_ENTITIES', 'VK_KG_RELATIONS', 'VK_KNOWLEDGE_GRAPH') ORDER BY object_name"
                )
            ).all()
            print("Existing objects:", [tuple(r) for r in existing])
            if not args.apply:
                print("Inspection only. Use --apply to install views/graph; Oracle DDL commits implicitly.")
                return
            if not privilege:
                raise SystemExit("CREATE PROPERTY GRAPH privilege required")
            for statement in DDL:
                connection.execute(text(statement))
            connection.commit()
            # Parse and execute the graph query without exposing stored user data.
            connection.execute(
                text("""SELECT version_id FROM GRAPH_TABLE (
                VK_KNOWLEDGE_GRAPH MATCH (s IS entity)-[e IS relation]->(t IS entity)
                WHERE e.owner_id = :owner
                COLUMNS (e.id AS version_id, s.id AS source_id, t.id AS target_id)
            ) WHERE source_id = :seed OR target_id = :seed"""),
                {"owner": "__installation_probe__", "seed": "__installation_probe__"},
            ).all()
            print("Property Graph installed; GRAPH_TABLE query verified. No source data copied or changed.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
