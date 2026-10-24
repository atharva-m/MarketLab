"""PostgreSQL durable daily ingestion, leases and fenced state transitions."""

import hashlib
import json
import re
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine

from .source import DatasetError, validate_scope

CONTRACT = "daily-ingestion-v1"
LEASE_SECONDS = 60
HEARTBEAT_SECONDS = 10
metadata = sa.MetaData()
submissions = sa.Table(
    "ingestion_submissions",
    metadata,
    sa.Column("submission_id", sa.String(36), primary_key=True),
    sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
    sa.Column("request_sha256", sa.String(64), nullable=False),
    sa.Column("symbols", sa.Text, nullable=False),
    sa.Column("start_date", sa.Date, nullable=False),
    sa.Column("before_date", sa.Date, nullable=False),
    sa.Column("execution_contract", sa.String(40), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)
jobs = sa.Table(
    "ingestion_jobs",
    metadata,
    sa.Column("job_id", sa.String(36), primary_key=True),
    sa.Column("submission_id", sa.String(36), nullable=False),
    sa.Column("venue", sa.String(32), nullable=False),
    sa.Column("symbol", sa.String(20), nullable=False),
    sa.Column("trade_date", sa.Date, nullable=False),
    sa.Column("source_mode", sa.String(16), nullable=False),
    sa.Column("input_sha256", sa.String(64)),
    sa.Column("state", sa.String(16), nullable=False),
    sa.Column("attempt_count", sa.Integer, nullable=False),
    sa.Column("fencing_token", sa.BigInteger, nullable=False),
    sa.Column("owner", sa.String(36)),
    sa.Column("lease_until", sa.DateTime(timezone=True)),
    sa.Column("eligible_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("result_version", sa.String(64)),
    sa.Column("error", sa.String(160)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)
attempts = sa.Table(
    "ingestion_attempts",
    metadata,
    sa.Column("job_id", sa.String(36), primary_key=True),
    sa.Column("attempt_number", sa.Integer, primary_key=True),
    sa.Column("fencing_token", sa.BigInteger, nullable=False),
    sa.Column("owner", sa.String(36), nullable=False),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("ended_at", sa.DateTime(timezone=True)),
    sa.Column("outcome", sa.String(16), nullable=False),
    sa.Column("error", sa.String(160)),
)


class OwnershipLost(DatasetError):
    """This attempt no longer has permission to mutate durable state."""


@dataclass(frozen=True)
class Claim:
    job_id: str
    submission_id: str
    symbol: str
    trade_date: date
    owner: str
    token: int
    attempt: int
    lost: threading.Event = field(default_factory=threading.Event, compare=False)


def validate_request(symbols: Sequence[str], start: date, before: date, key: str) -> list[str]:
    if (
        not isinstance(key, str)
        or re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", key) is None
        or type(start) is not date
        or type(before) is not date
        or not symbols
        or len(symbols) > 2
        or len(set(symbols)) != len(symbols)
        or not date(2025, 1, 1) <= start < before <= date(2025, 2, 1)
    ):
        raise DatasetError("invalid historical submission")
    for symbol in symbols:
        validate_scope(symbol, start)
    return sorted(symbols)


def submit(
    engine: Engine,
    symbols: Sequence[str],
    start: date,
    before: date,
    key: str,
    *,
    source_mode: str = "official",
    input_sha256: str | None = None,
) -> str:
    ordered = validate_request(symbols, start, before, key)
    if source_mode not in {"official", "inline", "fixture"} or (source_mode == "fixture") != (
        input_sha256 is not None
    ):
        raise DatasetError("invalid ingestion source mode")
    if input_sha256 is not None and re.fullmatch(r"[0-9a-f]{64}", input_sha256) is None:
        raise DatasetError("invalid ingestion source identity")
    payload = json.dumps(
        [CONTRACT, ordered, start.isoformat(), before.isoformat(), source_mode, input_sha256],
        separators=(",", ":"),
    )
    digest = hashlib.sha256(payload.encode()).hexdigest()
    with engine.begin() as connection:
        connection.execute(sa.text("SET LOCAL lock_timeout = '10s'"))
        lock = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big", signed=True)
        connection.execute(sa.text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock})
        existing = (
            connection.execute(sa.select(submissions).where(submissions.c.idempotency_key == key))
            .mappings()
            .one_or_none()
        )
        if existing is not None:
            if existing["request_sha256"] != digest:
                raise DatasetError("submission key conflicts with existing request")
            return str(existing["submission_id"])
        submission = str(uuid4())
        now = connection.scalar(sa.select(sa.func.clock_timestamp()))
        connection.execute(
            submissions.insert().values(
                submission_id=submission,
                idempotency_key=key,
                request_sha256=digest,
                symbols=json.dumps(ordered),
                start_date=start,
                before_date=before,
                execution_contract=CONTRACT,
                created_at=now,
            )
        )
        values = []
        for offset in range((before - start).days):
            for symbol in ordered:
                values.append(
                    dict(
                        job_id=str(uuid4()),
                        submission_id=submission,
                        venue="binance_spot",
                        symbol=symbol,
                        trade_date=start + timedelta(days=offset),
                        source_mode=source_mode,
                        input_sha256=input_sha256,
                        state="queued",
                        attempt_count=0,
                        fencing_token=0,
                        eligible_at=now,
                        created_at=now,
                        updated_at=now,
                    )
                )
        connection.execute(jobs.insert(), values)
        return submission


def claim(
    engine: Engine, *, submission_id: str | None = None, job_id: str | None = None
) -> Claim | None:
    with engine.begin() as connection:
        now = sa.func.clock_timestamp()
        eligible = sa.or_(
            sa.and_(jobs.c.state.in_(["queued", "retry_wait"]), jobs.c.eligible_at <= now),
            sa.and_(jobs.c.state == "running", jobs.c.lease_until <= now),
        )
        query = sa.select(jobs).where(
            eligible,
            jobs.c.submission_id.in_(
                sa.select(submissions.c.submission_id).where(
                    submissions.c.execution_contract == CONTRACT
                )
            ),
        )
        if submission_id is not None:
            query = query.where(jobs.c.submission_id == submission_id)
        if job_id is not None:
            query = query.where(jobs.c.job_id == job_id)
        else:
            query = query.where(jobs.c.source_mode == "official")
        while True:
            row = (
                connection.execute(
                    query.order_by(jobs.c.created_at, jobs.c.trade_date, jobs.c.symbol)
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                return None
            if row["state"] == "running":
                connection.execute(
                    attempts.update()
                    .where(
                        attempts.c.job_id == row["job_id"],
                        attempts.c.attempt_number == row["attempt_count"],
                    )
                    .values(outcome="expired", ended_at=now, error="worker lease expired")
                )
            if row["attempt_count"] >= 3:
                connection.execute(
                    jobs.update()
                    .where(jobs.c.job_id == row["job_id"])
                    .values(
                        state="failed",
                        owner=None,
                        lease_until=None,
                        error="attempt budget exhausted",
                        updated_at=now,
                    )
                )
                continue
            owner = str(uuid4())
            token, number = row["fencing_token"] + 1, row["attempt_count"] + 1
            connection.execute(
                jobs.update()
                .where(jobs.c.job_id == row["job_id"])
                .values(
                    state="running",
                    owner=owner,
                    lease_until=now + sa.text("INTERVAL '60 seconds'"),
                    attempt_count=number,
                    fencing_token=token,
                    error=None,
                    updated_at=now,
                )
            )
            connection.execute(
                attempts.insert().values(
                    job_id=row["job_id"],
                    attempt_number=number,
                    fencing_token=token,
                    owner=owner,
                    started_at=now,
                    outcome="running",
                )
            )
            return Claim(
                row["job_id"],
                row["submission_id"],
                row["symbol"],
                row["trade_date"],
                owner,
                token,
                number,
            )


def _owned(current: Claim) -> Any:
    return sa.and_(
        jobs.c.job_id == current.job_id,
        jobs.c.state == "running",
        jobs.c.owner == current.owner,
        jobs.c.fencing_token == current.token,
        jobs.c.lease_until > sa.func.clock_timestamp(),
    )


def heartbeat(engine: Engine, current: Claim) -> bool:
    with engine.begin() as connection:
        result = connection.execute(
            jobs.update()
            .where(_owned(current))
            .values(
                lease_until=sa.func.clock_timestamp() + sa.text("INTERVAL '60 seconds'"),
                updated_at=sa.func.clock_timestamp(),
            )
        )
        return result.rowcount == 1


def fence(connection: Connection, current: Claim) -> None:
    if current.lost.is_set():
        raise OwnershipLost("ingestion ownership lost")
    row = connection.execute(
        sa.select(jobs.c.job_id).where(_owned(current)).with_for_update()
    ).one_or_none()
    if row is None:
        raise OwnershipLost("ingestion ownership lost")


def succeed(connection: Connection, current: Claim, version: str) -> None:
    if current.lost.is_set():
        raise OwnershipLost("ingestion ownership lost")
    result = connection.execute(
        jobs.update()
        .where(_owned(current))
        .values(
            state="succeeded",
            result_version=version,
            owner=None,
            lease_until=None,
            error=None,
            updated_at=sa.func.clock_timestamp(),
        )
    )
    if result.rowcount != 1:
        raise OwnershipLost("ingestion ownership lost")
    connection.execute(
        attempts.update()
        .where(attempts.c.job_id == current.job_id, attempts.c.fencing_token == current.token)
        .values(outcome="succeeded", ended_at=sa.func.clock_timestamp())
    )


def fail(engine: Engine, current: Claim, error: Exception) -> None:
    from .source import TransientSourceError

    transient = isinstance(error, TransientSourceError)
    cause: BaseException | None = error
    while cause is not None:
        if isinstance(cause, sa.exc.DBAPIError):
            transient = getattr(cause.orig, "sqlstate", None) in {
                "40001",
                "40P01",
                "55P03",
                "57014",
                "08006",
                "08003",
            }
            break
        cause = cause.__cause__
    retry = transient and current.attempt < 3
    message = "transient ingestion failure" if transient else "historical ingestion failed"
    delay = 10 if current.attempt == 1 else 30
    if isinstance(error, TransientSourceError):
        delay = max(delay, error.retry_after)
    with engine.begin() as connection:
        result = connection.execute(
            jobs.update()
            .where(_owned(current))
            .values(
                state="retry_wait" if retry else "failed",
                owner=None,
                lease_until=None,
                error=message,
                eligible_at=sa.func.clock_timestamp() + timedelta(seconds=delay),
                updated_at=sa.func.clock_timestamp(),
            )
        )
        if result.rowcount != 1:
            raise OwnershipLost("ingestion ownership lost")
        connection.execute(
            attempts.update()
            .where(attempts.c.job_id == current.job_id, attempts.c.fencing_token == current.token)
            .values(
                outcome="transient" if transient else "permanent",
                error=message,
                ended_at=sa.func.clock_timestamp(),
            )
        )


def inspect_submission(engine: Engine, submission_id: str) -> dict[str, Any]:
    if re.fullmatch(r"[0-9a-f-]{36}", submission_id) is None:
        raise DatasetError("invalid submission identity")
    with engine.connect() as connection:
        submission = (
            connection.execute(
                sa.select(submissions).where(submissions.c.submission_id == submission_id)
            )
            .mappings()
            .one_or_none()
        )
        if submission is None:
            raise DatasetError("submission not found")
        rows = [
            dict(row)
            for row in connection.execute(
                sa.select(jobs)
                .where(jobs.c.submission_id == submission_id)
                .order_by(jobs.c.trade_date, jobs.c.symbol)
                .limit(62)
            ).mappings()
        ]
        for row in rows:
            row["attempts"] = [
                dict(item)
                for item in connection.execute(
                    sa.select(attempts)
                    .where(attempts.c.job_id == row["job_id"])
                    .order_by(attempts.c.attempt_number)
                ).mappings()
            ]
    return {
        "submission": dict(submission),
        "jobs": rows,
        "total": len(rows),
        "succeeded": sum(row["state"] == "succeeded" for row in rows),
        "failed": sum(row["state"] == "failed" for row in rows),
        "complete": bool(rows) and all(row["state"] == "succeeded" for row in rows),
    }


def execute(
    engine: Engine, current: Claim, operation: Callable[[Claim], dict[str, object]]
) -> dict[str, object]:
    stop, lost = threading.Event(), current.lost

    def renew() -> None:
        while not stop.wait(HEARTBEAT_SECONDS):
            try:
                if not heartbeat(engine, current):
                    lost.set()
                    return
            except Exception:
                lost.set()
                return

    thread = threading.Thread(target=renew, name="ingestion-heartbeat", daemon=True)
    thread.start()
    try:
        if lost.is_set():
            raise OwnershipLost("ingestion ownership lost")
        return operation(current)
    except OwnershipLost:
        raise
    except Exception as error:
        fail(engine, current, error)
        raise
    finally:
        stop.set()
        thread.join(timeout=20)


def work(
    engine: Engine,
    operation: Callable[[Claim], dict[str, object]],
    *,
    max_jobs: int = 1,
    submission_id: str | None = None,
    wait_seconds: int = 0,
    stop_event: threading.Event | None = None,
) -> int:
    if (
        type(max_jobs) is not int
        or not 1 <= max_jobs <= 62
        or type(wait_seconds) is not int
        or not 0 <= wait_seconds <= 3600
    ):
        raise DatasetError("invalid worker bounds")
    completed = 0
    stop = stop_event or threading.Event()
    deadline = time.monotonic() + wait_seconds
    while completed < max_jobs and not stop.is_set():
        current = claim(engine, submission_id=submission_id)
        if current is None:
            if time.monotonic() >= deadline:
                break
            stop.wait(min(1, max(0, deadline - time.monotonic())))
            continue
        try:
            execute(engine, current, operation)
        except (DatasetError, sa.exc.SQLAlchemyError, OSError):
            pass
        completed += 1
    return completed
