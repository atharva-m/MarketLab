"""Real bounded read-only monitoring connections independent of worker pools."""

import os
from uuid import uuid4

import pytest
import sqlalchemy as sa

from marketlab.config import Settings
from marketlab.monitoring import TABLES, collect_jobs, collector_engine

pytestmark = pytest.mark.integration


@pytest.fixture
def owned_monitor_engine():
    if "MARKETLAB_DATABASE_URL" not in os.environ:
        pytest.skip("requires owned migrated PostgreSQL")
    settings = Settings()
    admin = sa.create_engine(settings.sqlalchemy_url, connect_args=settings.database_connect_args)
    schema = "test_monitor_" + uuid4().hex
    with admin.begin() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        for table in TABLES.values():
            connection.exec_driver_sql(
                f'CREATE TABLE "{schema}".{table} '
                "(state text, attempt_count integer, created_at timestamptz)"
            )
        connection.exec_driver_sql(
            f'INSERT INTO "{schema}".memo_jobs VALUES '
            "('queued', 2, clock_timestamp()-interval '20 seconds'),"
            "('ready', 1, clock_timestamp())"
        )
    url = settings.sqlalchemy_url.update_query_dict({"options": f"-csearch_path={schema}"})
    reader = collector_engine(
        Settings(database_url=url.render_as_string(hide_password=False), database_password=None)
    )
    try:
        yield reader, admin, schema
    finally:
        reader.dispose()
        with admin.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        admin.dispose()


def test_real_collector_preserves_schema_and_read_only_bounds(
    owned_monitor_engine,
):
    reader, _, _ = owned_monitor_engine
    rows = collect_jobs(reader)
    assert len(rows) == 2
    queued = next(row for row in rows if row[1] == "queued")
    assert queued[:5] == ("memo", "queued", 1, 2, 1)
    assert queued[5] >= 20
    with reader.connect() as connection:
        assert connection.exec_driver_sql("SHOW transaction_read_only").scalar_one() == "on"
        assert connection.exec_driver_sql("SHOW statement_timeout").scalar_one() == "1s"
        assert connection.exec_driver_sql("SHOW lock_timeout").scalar_one() == "250ms"
        with pytest.raises(sa.exc.DBAPIError):
            connection.exec_driver_sql("DELETE FROM memo_jobs")


def test_real_collector_lock_timeout_does_not_hold_worker_connection(owned_monitor_engine):
    reader, admin, schema = owned_monitor_engine
    with admin.connect() as worker:
        with worker.begin():
            worker.exec_driver_sql(f'LOCK TABLE "{schema}".memo_jobs IN ACCESS EXCLUSIVE MODE')
            with pytest.raises(sa.exc.DBAPIError):
                collect_jobs(reader)
            assert worker.exec_driver_sql("SELECT 1").scalar_one() == 1
    assert len(collect_jobs(reader)) == 2
