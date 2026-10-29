"""Migration environment reads exactly the same validated DB settings as the app."""

from alembic import context

from example_app.models import Base
from python_foundation.database import create_database
from python_foundation.settings import FoundationSettings

settings = FoundationSettings()
if context.is_offline_mode():
    context.configure(
        url=settings.database_url.get_secret_value(),
        target_metadata=Base.metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_database(settings)
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()
