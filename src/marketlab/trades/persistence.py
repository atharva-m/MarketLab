"""Transactional persistence of supported in-memory synthetic batch formats."""

from sqlalchemy import Column, DateTime, MetaData, Numeric, String, Table, insert, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from marketlab.trades.parsers import parse_trades_csv, parse_trades_json
from marketlab.trades.schemas import Trade

metadata = MetaData()
trades = Table(
    "trades",
    metadata,
    Column("trade_id", String(64), primary_key=True),
    Column("symbol", String(20), nullable=False),
    Column("executed_at", DateTime(timezone=True), nullable=False),
    Column("price", Numeric(20, 8), nullable=False),
    Column("quantity", Numeric(20, 8), nullable=False),
)


class DuplicateTradeError(ValueError):
    """A stored ID conflicts with the batch; no batch records were committed."""


def _persist(engine: Engine, batch: tuple[Trade, ...]) -> int:
    if not batch:
        return 0
    try:
        with engine.begin() as connection:
            connection.execute(insert(trades), [trade.model_dump() for trade in batch])
    except IntegrityError as error:
        # The primary key arbitrates concurrent imports. Other failures must propagate.
        original = error.orig
        if (
            getattr(original, "sqlstate", None) == "23505"
            and getattr(getattr(original, "diag", None), "constraint_name", None) == "trades_pkey"
        ):
            raise DuplicateTradeError("batch contains an already stored trade_id") from error
        raise
    return len(batch)


def import_trades_json(engine: Engine, payload: str) -> int:
    """Validate the entire JSON batch, commit it atomically, and return its size."""
    return _persist(engine, parse_trades_json(payload))


def import_trades_csv(engine: Engine, payload: str) -> int:
    """Validate the entire CSV batch, commit it atomically, and return its size."""
    return _persist(engine, parse_trades_csv(payload))


def get_trade(engine: Engine, trade_id: str) -> Trade | None:
    """Return a trade by its exact, case-sensitive ID, normalized to UTC, or None."""
    with engine.connect() as connection:
        # Normalize in PostgreSQL before psycopg decodes the timestamp. A session
        # offset can otherwise push a valid year 1/9999 instant outside Python's
        # datetime range. LOCAL resets when this read transaction ends.
        connection.execute(text("SET LOCAL TIME ZONE 'UTC'"))
        record = (
            connection.execute(select(trades).where(trades.c.trade_id == trade_id))
            .mappings()
            .one_or_none()
        )
    return Trade.model_validate(dict(record)) if record is not None else None
