"""Read-only DB verification. Never prints credentials or connection strings."""

from sqlalchemy import text

from knowledge_app.database import database
from knowledge_app.settings import Settings

engine = database(Settings())
try:
    with engine.connect() as con:
        print("Connection: OK")
        if engine.dialect.name == "oracle":
            print(
                "Version:",
                con.scalar(text("SELECT version_full FROM product_component_version FETCH FIRST 1 ROW ONLY")),
            )
            print(
                "Vector distance:",
                con.scalar(
                    text("SELECT VECTOR_DISTANCE(TO_VECTOR('[1,0]'),TO_VECTOR('[1,0]'),COSINE) FROM dual")
                ),
            )
finally:
    engine.dispose()
