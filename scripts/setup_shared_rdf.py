"""Create the shared assertion model in the dedicated knowledge RDF network."""

from sqlalchemy import text

from knowledge_app.database import database
from knowledge_app.settings import Settings


def main() -> None:
    engine = database(Settings())
    try:
        if engine.dialect.name != "oracle":
            raise SystemExit("Oracle required")
        with engine.connect() as connection:
            count = connection.scalar(
                text(
                    "SELECT COUNT(*) FROM USER_OBJECTS WHERE OBJECT_NAME='VK_FLOW_RDF#RDFT_VK_SHARED' AND OBJECT_TYPE='VIEW' AND STATUS='VALID'"
                )
            )
            if count:
                print("Shared RDF view exists; no changes made")
                return
            connection.execute(
                text(
                    "BEGIN SEM_APIS.CREATE_RDF_GRAPH('VK_SHARED',NULL,NULL,network_owner=>USER,network_name=>'VK_FLOW_RDF'); END;"
                )
            )
            connection.commit()
        print("Created shared RDF model VK_SHARED in VK_FLOW_RDF")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
