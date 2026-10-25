"""Separate PostgreSQL research records and fenced durable state transitions."""

import hashlib
import json
import re
import threading
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine

from marketlab.analytics.cache import canonical

from .spec import ResearchError

metadata = sa.MetaData()
submissions = sa.Table(
    "research_submissions",
    metadata,
    sa.Column("submission_id", sa.String(36), primary_key=True),
    sa.Column("idempotency_key", sa.String(128), nullable=False),
    sa.Column("request_sha256", sa.String(64), nullable=False),
    sa.Column("spec", sa.Text, nullable=False),
    sa.Column("fingerprint", sa.Text, nullable=False),
    sa.Column("fingerprint_sha256", sa.String(64), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)
runs = sa.Table(
    "research_runs",
    metadata,
    sa.Column("run_id", sa.String(36), primary_key=True),
    sa.Column("submission_id", sa.String(36), nullable=False),
    sa.Column("state", sa.String(16), nullable=False),
    sa.Column("attempt_count", sa.Integer, nullable=False),
    sa.Column("fencing_token", sa.BigInteger, nullable=False),
    sa.Column("owner", sa.String(36)),
    sa.Column("lease_until", sa.DateTime(timezone=True)),
    sa.Column("eligible_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("result_id", sa.String(36)),
    sa.Column("error", sa.String(160)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)
attempts = sa.Table(
    "research_attempts",
    metadata,
    sa.Column("run_id", sa.String(36), primary_key=True),
    sa.Column("attempt_number", sa.Integer, primary_key=True),
    sa.Column("fencing_token", sa.BigInteger, nullable=False),
    sa.Column("owner", sa.String(36), nullable=False),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("ended_at", sa.DateTime(timezone=True)),
    sa.Column("outcome", sa.String(16), nullable=False),
    sa.Column("error", sa.String(160)),
)
results = sa.Table(
    "research_results",
    metadata,
    sa.Column("run_id", sa.String(36), primary_key=True),
    sa.Column("manifest_sha256", sa.String(64), nullable=False),
    sa.Column("manifest_path", sa.Text, nullable=False),
    sa.Column("results_sha256", sa.String(64), nullable=False),
    sa.Column("summary_sha256", sa.String(64), nullable=False),
    sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
)


@dataclass(frozen=True)
class Claim:
    run_id: str
    owner: str
    token: int
    attempt: int
    lost: threading.Event = field(default_factory=threading.Event, compare=False)


def bounded(connection: Connection) -> None:
    for setting, value in (
        ("lock_timeout", "10s"),
        ("statement_timeout", "15s"),
        ("idle_in_transaction_session_timeout", "15s"),
    ):
        connection.execute(sa.text(f"SET LOCAL {setting} = '{value}'"))


def advisory(connection: Connection, identity: str) -> None:
    key = int.from_bytes(
        hashlib.sha256(("research:" + identity).encode()).digest()[:8], "big", signed=True
    )
    connection.execute(sa.text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


def replay(engine: Engine, key: str, digest: str) -> str | None:
    if re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", key) is None:
        raise ResearchError("Invalid research idempotency key")
    with engine.connect() as connection:
        row = (
            connection.execute(
                sa.select(submissions, runs.c.run_id)
                .join(runs, runs.c.submission_id == submissions.c.submission_id)
                .where(submissions.c.idempotency_key == key)
            )
            .mappings()
            .one_or_none()
        )
    if row is None:
        return None
    if row["request_sha256"] != digest:
        raise ResearchError("Research idempotency key conflict", 409)
    return str(row["run_id"])


def submit(
    engine: Engine, key: str, spec: dict[str, Any], fingerprint: dict[str, Any]
) -> tuple[str, bool]:
    digest = hashlib.sha256(canonical(spec)).hexdigest()
    replay(engine, key, digest)
    with engine.begin() as connection:
        bounded(connection)
        advisory(connection, "submission:" + key)
        row = (
            connection.execute(
                sa.select(submissions, runs.c.run_id)
                .join(runs, runs.c.submission_id == submissions.c.submission_id)
                .where(submissions.c.idempotency_key == key)
            )
            .mappings()
            .one_or_none()
        )
        if row:
            if row["request_sha256"] != digest:
                raise ResearchError("Research idempotency key conflict", 409)
            return str(row["run_id"]), True
        submission, run = str(uuid4()), str(uuid4())
        now = connection.scalar(sa.select(sa.func.clock_timestamp()))
        connection.execute(
            submissions.insert().values(
                submission_id=submission,
                idempotency_key=key,
                request_sha256=digest,
                spec=canonical(spec).decode(),
                fingerprint=canonical(fingerprint).decode(),
                fingerprint_sha256=hashlib.sha256(canonical(fingerprint)).hexdigest(),
                created_at=now,
            )
        )
        connection.execute(
            runs.insert().values(
                run_id=run,
                submission_id=submission,
                state="queued",
                attempt_count=0,
                fencing_token=0,
                eligible_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        return run, False


def claim(engine: Engine, run_id: str | None = None) -> Claim | None:
    with engine.begin() as connection:
        bounded(connection)
        now = sa.func.clock_timestamp()
        query = sa.select(runs).where(
            sa.or_(
                sa.and_(runs.c.state.in_(["queued", "retry_wait"]), runs.c.eligible_at <= now),
                sa.and_(runs.c.state == "running", runs.c.lease_until <= now),
            )
        )
        if run_id:
            query = query.where(runs.c.run_id == run_id)
        while True:
            row = (
                connection.execute(
                    query.order_by(runs.c.created_at, runs.c.run_id)
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
                        attempts.c.run_id == row["run_id"],
                        attempts.c.attempt_number == row["attempt_count"],
                    )
                    .values(outcome="expired", ended_at=now)
                )
            if row["attempt_count"] >= 3:
                connection.execute(
                    runs.update()
                    .where(runs.c.run_id == row["run_id"])
                    .values(
                        state="failed",
                        owner=None,
                        lease_until=None,
                        error="Research attempt budget exhausted",
                        updated_at=now,
                    )
                )
                continue
            owner = str(uuid4())
            current = Claim(
                row["run_id"], owner, row["fencing_token"] + 1, row["attempt_count"] + 1
            )
            connection.execute(
                runs.update()
                .where(runs.c.run_id == current.run_id)
                .values(
                    state="running",
                    owner=owner,
                    lease_until=now + timedelta(seconds=60),
                    attempt_count=current.attempt,
                    fencing_token=current.token,
                    error=None,
                    updated_at=now,
                )
            )
            connection.execute(
                attempts.insert().values(
                    run_id=current.run_id,
                    attempt_number=current.attempt,
                    fencing_token=current.token,
                    owner=owner,
                    started_at=now,
                    outcome="running",
                )
            )
            return current


def owned(current: Claim) -> Any:
    return sa.and_(
        runs.c.run_id == current.run_id,
        runs.c.state == "running",
        runs.c.owner == current.owner,
        runs.c.fencing_token == current.token,
        runs.c.lease_until > sa.func.clock_timestamp(),
    )


def fence(connection: Connection, current: Claim) -> None:
    if (
        current.lost.is_set()
        or connection.execute(
            sa.select(runs.c.run_id).where(owned(current)).with_for_update()
        ).first()
        is None
    ):
        raise ResearchError("Research ownership lost", 409)


def heartbeat(engine: Engine, current: Claim) -> bool:
    with engine.begin() as connection:
        bounded(connection)
        result = connection.execute(
            runs.update()
            .where(owned(current))
            .values(
                lease_until=sa.func.clock_timestamp() + timedelta(seconds=60),
                updated_at=sa.func.clock_timestamp(),
            )
        )
        return result.rowcount == 1


def finish(connection: Connection, current: Claim) -> None:
    fence(connection, current)
    now = sa.func.clock_timestamp()
    result = connection.execute(
        runs.update()
        .where(owned(current))
        .values(
            state="succeeded",
            result_id=current.run_id,
            owner=None,
            lease_until=None,
            updated_at=now,
        )
    )
    if result.rowcount != 1:
        raise ResearchError("Research ownership lost", 409)
    connection.execute(
        attempts.update()
        .where(
            attempts.c.run_id == current.run_id,
            attempts.c.attempt_number == current.attempt,
            attempts.c.fencing_token == current.token,
            attempts.c.owner == current.owner,
        )
        .values(outcome="succeeded", ended_at=now)
    )


def fail(engine: Engine, current: Claim, transient: bool = False) -> None:
    with engine.begin() as connection:
        bounded(connection)
        fence(connection, current)
        now = sa.func.clock_timestamp()
        retry = transient and current.attempt < 3
        message = (
            "Transient research execution failure" if transient else "Research execution failed"
        )
        result = connection.execute(
            runs.update()
            .where(owned(current))
            .values(
                state="retry_wait" if retry else "failed",
                owner=None,
                lease_until=None,
                error=message,
                eligible_at=now + timedelta(seconds=10 if current.attempt == 1 else 30),
                updated_at=now,
            )
        )
        if result.rowcount != 1:
            raise ResearchError("Research ownership lost", 409)
        connection.execute(
            attempts.update()
            .where(
                attempts.c.run_id == current.run_id,
                attempts.c.attempt_number == current.attempt,
                attempts.c.fencing_token == current.token,
                attempts.c.owner == current.owner,
            )
            .values(outcome="transient" if transient else "permanent", error=message, ended_at=now)
        )


def inspect(engine: Engine, run_id: str) -> dict[str, Any]:
    if re.fullmatch(r"[0-9a-f-]{36}", run_id) is None:
        raise ResearchError("Invalid research run identity")
    with engine.connect() as connection:
        row = (
            connection.execute(
                sa.select(runs, submissions.c.spec, submissions.c.fingerprint)
                .join(submissions, runs.c.submission_id == submissions.c.submission_id)
                .where(runs.c.run_id == run_id)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise ResearchError("Research run not found", 404)
        history = (
            connection.execute(
                sa.select(attempts)
                .where(attempts.c.run_id == run_id)
                .order_by(attempts.c.attempt_number)
            )
            .mappings()
            .all()
        )
    body = dict(row)
    for name in ("spec", "fingerprint"):
        body[name] = json.loads(body[name])
    body["attempts"] = [dict(item) for item in history]
    return body
