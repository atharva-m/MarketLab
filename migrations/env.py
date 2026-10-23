from alembic import context
from sqlalchemy import create_engine, pool

from marketlab.config import Settings

config = context.config
settings = Settings()
url = settings.sqlalchemy_url
target_metadata = None

if context.is_offline_mode():
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    connectable = create_engine(
        url, poolclass=pool.NullPool, connect_args=settings.database_connect_args
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()
