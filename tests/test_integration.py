import os
from pathlib import Path

import httpx
import pytest
from sqlalchemy import DateTime, Numeric, create_engine, inspect, text

from marketlab.app import create_app
from marketlab.config import Settings

pytestmark = pytest.mark.integration


async def test_real_postgres_and_readiness(tmp_path: Path) -> None:
    if "MARKETLAB_DATABASE_URL" not in os.environ:
        pytest.skip("Set MARKETLAB_DATABASE_URL to a migrated PostgreSQL instance")
    settings = Settings(
        storage_path=tmp_path,
        redis_url="redis://127.0.0.1:1/0",
        ollama_url="http://127.0.0.1:1",
        dependency_timeout_seconds=3,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/health/ready")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "degraded", response.text
    assert response.json()["checks"]["postgresql"]["status"] == "up", response.text
    assert response.json()["checks"]["storage"]["status"] == "up", response.text


def test_trade_migration() -> None:
    if "MARKETLAB_DATABASE_URL" not in os.environ:
        pytest.skip("Set MARKETLAB_DATABASE_URL to a migrated PostgreSQL instance")
    settings = Settings()
    engine = create_engine(
        settings.sqlalchemy_url,
        pool_timeout=settings.database_connect_timeout_seconds,
        connect_args=settings.database_connect_args,
    )
    try:
        with engine.connect() as connection:
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            tables = (
                connection.execute(
                    text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                )
                .scalars()
                .all()
            )
        assert revision == "0008_v2_ingestion"
        assert set(tables) == {
            "alembic_version",
            "trades",
            "dataset_versions",
            "ingestion_submissions",
            "ingestion_jobs",
            "ingestion_attempts",
            "research_submissions",
            "research_runs",
            "research_attempts",
            "research_results",
            "copilot_requests",
            "copilot_revisions",
            "copilot_jobs",
            "copilot_attempts",
            "memo_jobs",
            "memo_attempts",
            "memo_results",
            "v2_instruments",
            "v2_operations",
            "v2_ingestion_submissions",
            "v2_canonical_imports",
            "v2_ingestion_jobs",
            "v2_ingestion_attempts",
            "v2_dataset_versions",
            "v2_storage_reservations",
        }
        inspector = inspect(engine)
        columns = {column["name"]: column for column in inspector.get_columns("trades")}
        assert set(columns) == {"trade_id", "symbol", "executed_at", "price", "quantity"}
        assert all(not column["nullable"] for column in columns.values())
        assert columns["trade_id"]["type"].length == 64
        assert columns["symbol"]["type"].length == 20
        assert isinstance(columns["executed_at"]["type"], DateTime)
        assert columns["executed_at"]["type"].timezone
        for name in ("price", "quantity"):
            numeric = columns[name]["type"]
            assert isinstance(numeric, Numeric)
            assert (numeric.precision, numeric.scale) == (20, 8)
        assert inspector.get_pk_constraint("trades")["constrained_columns"] == ["trade_id"]
    finally:
        engine.dispose()
