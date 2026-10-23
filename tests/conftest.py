import asyncio
import os
from collections.abc import Callable, Iterator
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from marketlab.config import Settings


def pytest_asyncio_loop_factories() -> dict[str, Callable[[], asyncio.AbstractEventLoop]]:
    # Psycopg async connections require the selector loop on Windows.
    return {"selector": asyncio.SelectorEventLoop}


@pytest.fixture
def trade_engine() -> Iterator[Engine]:
    if "MARKETLAB_DATABASE_URL" not in os.environ:
        pytest.skip("Set MARKETLAB_DATABASE_URL to a disposable, migrated PostgreSQL instance")
    settings = Settings()
    engine = create_engine(
        settings.sqlalchemy_url,
        pool_timeout=settings.database_connect_timeout_seconds,
        connect_args={**settings.database_connect_args, "options": "-c timezone=Pacific/Honolulu"},
    )
    # Clone the actual migrated table, including constraints, into an isolated test
    # schema. Never truncate shared tables or leave committed synthetic test records.
    schema = "test_trades_" + uuid4().hex
    isolated = engine.execution_options(schema_translate_map={None: schema})
    try:
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(
                text(f'CREATE TABLE "{schema}".trades (LIKE public.trades INCLUDING ALL)')
            )
        yield isolated
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()
