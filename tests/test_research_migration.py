"""Execute real fresh/populated migrations, including actual foreign keys."""

from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from test_jobs_integration import migration_module

from marketlab.research import store

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("populated", [False, True])
def test_actual_fresh_populated_migration_preservation_and_constraints(dataset_engine, populated):
    schema = "test_r4_migration_" + uuid4().hex
    with dataset_engine.begin() as connection:
        connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
    try:
        with dataset_engine.begin() as connection:
            connection = connection.execution_options(schema_translate_map={None: schema})
            connection.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
            with Operations.context(MigrationContext.configure(connection)):
                for name in ("0002_trades", "0003_dataset_versions", "0004_ingestion_jobs"):
                    migration_module(name).upgrade()
                if populated:
                    connection.execute(
                        sa.text(
                            "INSERT INTO trades VALUES "
                            "('old','SYN','2025-01-01T00:00:00Z',1.25,2.5)"
                        )
                    )
                    connection.execute(
                        sa.text(
                            "INSERT INTO dataset_versions VALUES "
                            "(:v,:s,:m,'old-manifest','binance_spot','BTCUSDT','2025-01-01',7,"
                            "'published',CURRENT_TIMESTAMP)"
                        ),
                        {"v": "a" * 64, "s": "b" * 64, "m": "c" * 64},
                    )
                    connection.execute(
                        sa.text(
                            "INSERT INTO ingestion_submissions VALUES "
                            "('old-submission','old-key',:h,'[\"BTCUSDT\"]','2025-01-01','2025-01-02',"
                            "'daily-ingestion-v1',CURRENT_TIMESTAMP)"
                        ),
                        {"h": "d" * 64},
                    )
                    connection.execute(
                        sa.text(
                            "INSERT INTO ingestion_jobs "
                            "(job_id,submission_id,venue,symbol,trade_date,source_mode,state,attempt_count,"
                            "fencing_token,eligible_at,result_version,created_at,updated_at) "
                            "VALUES "
                            "('old-job','old-submission','binance_spot','BTCUSDT','2025-01-01',"
                            "'official','succeeded',1,1,CURRENT_TIMESTAMP,:v,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
                        ),
                        {"v": "a" * 64},
                    )
                    connection.execute(
                        sa.text(
                            "INSERT INTO ingestion_attempts VALUES "
                            "('old-job',1,1,'old-owner',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,'succeeded',NULL)"
                        )
                    )
                retained = {
                    table: connection.execute(sa.text(f"SELECT * FROM {table}")).all()
                    for table in (
                        "trades",
                        "dataset_versions",
                        "ingestion_submissions",
                        "ingestion_jobs",
                        "ingestion_attempts",
                    )
                }
                migration_module("0005_research").upgrade()
                for table, rows in retained.items():
                    assert connection.execute(sa.text(f"SELECT * FROM {table}")).all() == rows
                foreign = connection.scalar(
                    sa.text(
                        "SELECT count(*) FROM pg_constraint WHERE "
                        "connamespace=CAST(:schema AS regnamespace) AND contype='f'"
                    ),
                    {"schema": schema},
                )
                assert foreign == 6
                sid, rid = str(uuid4()), str(uuid4())
                now = sa.func.clock_timestamp()
                connection.execute(
                    store.submissions.insert().values(
                        submission_id=sid,
                        idempotency_key="constraints",
                        request_sha256="e" * 64,
                        spec="{}",
                        fingerprint="{}",
                        fingerprint_sha256="f" * 64,
                        created_at=now,
                    )
                )
                valid = dict(
                    run_id=rid,
                    submission_id=sid,
                    state="queued",
                    attempt_count=0,
                    fencing_token=0,
                    eligible_at=now,
                    created_at=now,
                    updated_at=now,
                )
                connection.execute(store.runs.insert().values(**valid))
                for invalid in (
                    {"attempt_count": 4},
                    {"fencing_token": -1},
                    {"state": "running"},
                    {"owner": "unexpected"},
                    {"state": "succeeded"},
                    {"submission_id": str(uuid4())},
                    {"result_id": str(uuid4())},
                ):
                    with pytest.raises(sa.exc.IntegrityError), connection.begin_nested():
                        connection.execute(
                            store.runs.update().where(store.runs.c.run_id == rid).values(**invalid)
                        )
                attempt = dict(
                    run_id=rid,
                    attempt_number=1,
                    fencing_token=1,
                    owner=str(uuid4()),
                    started_at=now,
                    outcome="running",
                )
                for invalid in (
                    {"run_id": str(uuid4())},
                    {"attempt_number": 0},
                    {"fencing_token": 0},
                    {"outcome": "expired"},
                ):
                    with pytest.raises(sa.exc.IntegrityError), connection.begin_nested():
                        connection.execute(store.attempts.insert().values(attempt | invalid))
                with pytest.raises(sa.exc.IntegrityError), connection.begin_nested():
                    connection.execute(
                        store.results.insert().values(
                            run_id=str(uuid4()),
                            manifest_sha256="a" * 64,
                            manifest_path="unused",
                            results_sha256="b" * 64,
                            summary_sha256="c" * 64,
                            registered_at=now,
                        )
                    )
                migration_module("0005_research").downgrade()
                for table, rows in retained.items():
                    assert connection.execute(sa.text(f"SELECT * FROM {table}")).all() == rows
    finally:
        with dataset_engine.begin() as connection:
            connection.execute(sa.text(f'DROP SCHEMA "{schema}" CASCADE'))
