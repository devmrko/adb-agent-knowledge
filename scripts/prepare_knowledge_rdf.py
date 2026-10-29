"""Initialize missing knowledge RDF models; preserve existing graphs and stop on partial setup."""

from sqlalchemy import text

from knowledge_app.database import database
from knowledge_app.settings import Settings
from scripts import setup_navigation_rdf, setup_shared_rdf, setup_workflow_rdf


def main() -> None:
    engine = database(Settings())
    try:
        if engine.dialect.name != "oracle":
            raise SystemExit("Oracle is required")
        with engine.connect() as connection:
            count = connection.scalar(
                text("SELECT COUNT(*) FROM USER_OBJECTS WHERE OBJECT_NAME LIKE 'VK!_FLOW!_RDF#%' ESCAPE '!'")
            )
            flow = connection.scalar(
                text(
                    "SELECT COUNT(*) FROM USER_OBJECTS WHERE OBJECT_NAME='VK_FLOW_RDF#RDFT_VK_FLOW' AND OBJECT_TYPE='VIEW' AND STATUS='VALID'"
                )
            )
        if count and not flow:
            raise SystemExit(
                "Partial RDF namespace exists. Inspect it; no replacement or deletion attempted."
            )
    finally:
        engine.dispose()
    if not count:
        setup_workflow_rdf.main()
    setup_shared_rdf.main()
    setup_navigation_rdf.main()
    print("RDF initialization complete. Existing knowledge and graphs preserved.")


if __name__ == "__main__":
    main()
