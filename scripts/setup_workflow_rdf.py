"""Explicit isolated Oracle RDF setup. No existing namespace is replaced."""

from sqlalchemy import text

from knowledge_app.database import database
from knowledge_app.settings import Settings

SETUP = """
DECLARE
 n NUMBER;
 ts VARCHAR2(128);
BEGIN
 IF SYS_CONTEXT('USERENV','CURRENT_SCHEMA') <> USER THEN
  RAISE_APPLICATION_ERROR(-20001,'Connect as RDF owner');
 END IF;
 SELECT COUNT(*) INTO n FROM USER_OBJECTS WHERE OBJECT_NAME LIKE 'VK!_FLOW!_RDF#%' ESCAPE '!';
 IF n <> 0 THEN RAISE_APPLICATION_ERROR(-20002,'Namespace exists; inspect without replacement'); END IF;
 SELECT DEFAULT_TABLESPACE INTO ts FROM USER_USERS;
 IF ts IN ('SYSTEM','SYSAUX') THEN RAISE_APPLICATION_ERROR(-20003,'Use application tablespace'); END IF;
 SEM_APIS.CREATE_RDF_NETWORK(ts,network_owner=>USER,network_name=>'VK_FLOW_RDF');
 SEM_APIS.CREATE_RDF_GRAPH('VK_FLOW',NULL,NULL,network_owner=>USER,network_name=>'VK_FLOW_RDF');
END;
"""


def main() -> None:
    engine = database(Settings())
    try:
        if engine.dialect.name != "oracle":
            raise SystemExit("Oracle is required for native RDF setup")
        with engine.connect() as connection:
            connection.execute(text(SETUP))
            connection.commit()
        print("Created VK_FLOW_RDF / VK_FLOW. Set WORKFLOW_RDF_ENABLED=true after verification.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
