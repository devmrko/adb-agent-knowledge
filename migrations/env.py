from alembic import context

from knowledge_app import audit_models, graph_auto_models  # noqa: F401
from knowledge_app.database import database
from knowledge_app.models import Base
from knowledge_app.settings import Settings

settings = Settings()
if context.is_offline_mode():
    context.configure(
        url=settings.database_url,
        target_metadata=Base.metadata,
        literal_binds=True,
        version_table="vk_alembic_version",
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = database(settings)
    try:
        with engine.connect() as con:
            if engine.dialect.name == "sqlite":
                # Alembic batch rebuilds tables referenced by cyclic item/revision FKs.
                con.exec_driver_sql("PRAGMA foreign_keys=OFF")
                con.commit()
            context.configure(
                connection=con,
                target_metadata=Base.metadata,
                version_table="vk_alembic_version",
                compare_type=True,
            )
            with context.begin_transaction():
                context.run_migrations()
            if engine.dialect.name == "sqlite":
                violations = con.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
                if violations:
                    raise RuntimeError("Migration foreign key validation failed")
                con.commit()
                con.exec_driver_sql("PRAGMA foreign_keys=ON")
    finally:
        engine.dispose()
