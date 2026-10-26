"""Database-time fenced memo state, call reservations and immutable registration."""

import json
import threading
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine

from marketlab.analytics.cache import canonical
from marketlab.copilot.spec import digest, identity
from marketlab.research import store as research
from marketlab.research.spec import ResearchError

metadata = sa.MetaData()
jobs = sa.Table(
    "memo_jobs",
    metadata,
    sa.Column("run_id", sa.String(36), primary_key=True),
    sa.Column("numerical_manifest_sha256", sa.String(64)),
    sa.Column("summary_sha256", sa.String(64)),
    sa.Column("execution", sa.Text),
    sa.Column("execution_sha256", sa.String(64)),
    sa.Column("state", sa.String(16)),
    sa.Column("attempt_count", sa.Integer),
    sa.Column("model_calls", sa.Integer),
    sa.Column("fencing_token", sa.BigInteger),
    sa.Column("owner", sa.String(36)),
    sa.Column("lease_until", sa.DateTime(timezone=True)),
    sa.Column("eligible_at", sa.DateTime(timezone=True)),
    sa.Column("error", sa.String(160)),
    sa.Column("draft", sa.Text),
    sa.Column("provenance", sa.Text),
    sa.Column("result_sha256", sa.String(64)),
    sa.Column("created_at", sa.DateTime(timezone=True)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
)
attempts = sa.Table(
    "memo_attempts",
    metadata,
    sa.Column("run_id", sa.String(36), primary_key=True),
    sa.Column("attempt_number", sa.Integer, primary_key=True),
    sa.Column("fencing_token", sa.BigInteger),
    sa.Column("owner", sa.String(36)),
    sa.Column("started_at", sa.DateTime(timezone=True)),
    sa.Column("ended_at", sa.DateTime(timezone=True)),
    sa.Column("outcome", sa.String(16)),
    sa.Column("error", sa.String(160)),
)
results = sa.Table(
    "memo_results",
    metadata,
    sa.Column("run_id", sa.String(36), primary_key=True),
    sa.Column("manifest_path", sa.Text),
    sa.Column("manifest_sha256", sa.String(64)),
    sa.Column("memo_sha256", sa.String(64)),
    sa.Column("summary_sha256", sa.String(64)),
    sa.Column("registered_at", sa.DateTime(timezone=True)),
)


@dataclass(frozen=True)
class Claim:
    run_id: str
    owner: str
    token: int
    attempt: int
    lost: threading.Event = field(default_factory=threading.Event, compare=False)


def enqueue(connection: Connection, run_id: str, manifest_hash: str, summary_hash: str) -> bool:
    """Caller holds numerical run lock; same-run creation never resets existing state."""
    row = (
        connection.execute(sa.select(jobs).where(jobs.c.run_id == run_id)).mappings().one_or_none()
    )
    if row is not None:
        if (row["numerical_manifest_sha256"], row["summary_sha256"]) != (
            manifest_hash,
            summary_hash,
        ):
            raise ResearchError("Memo numerical identity mismatch", 409)
        return True
    now = sa.func.clock_timestamp()
    connection.execute(
        jobs.insert().values(
            run_id=run_id,
            numerical_manifest_sha256=manifest_hash,
            summary_sha256=summary_hash,
            state="queued",
            attempt_count=0,
            model_calls=0,
            fencing_token=0,
            eligible_at=now,
            created_at=now,
            updated_at=now,
        )
    )
    return False


def eligible() -> Any:
    now = sa.func.clock_timestamp()
    return sa.or_(
        jobs.c.state == "queued",
        sa.and_(jobs.c.state == "retry_wait", jobs.c.eligible_at <= now),
        sa.and_(jobs.c.state == "running", jobs.c.lease_until <= now),
    )


def claim(engine: Engine, run_id: str | None = None) -> Claim | None:
    if run_id is not None:
        identity(run_id)
    with engine.begin() as connection:
        research.bounded(connection)
        query = sa.select(jobs).where(eligible())
        if run_id is not None:
            query = query.where(jobs.c.run_id == run_id)
        while True:
            row = (
                connection.execute(
                    query.order_by(jobs.c.created_at, jobs.c.run_id)
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                return None
            now = sa.func.clock_timestamp()
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
                    jobs.update()
                    .where(jobs.c.run_id == row["run_id"])
                    .values(
                        state="failed",
                        owner=None,
                        lease_until=None,
                        error="Memo attempt budget exhausted",
                        updated_at=now,
                    )
                )
                continue
            current = Claim(
                row["run_id"], str(uuid4()), row["fencing_token"] + 1, row["attempt_count"] + 1
            )
            connection.execute(
                jobs.update()
                .where(jobs.c.run_id == current.run_id)
                .values(
                    state="running",
                    owner=current.owner,
                    fencing_token=current.token,
                    attempt_count=current.attempt,
                    lease_until=now + timedelta(seconds=60),
                    error=None,
                    updated_at=now,
                )
            )
            connection.execute(
                attempts.insert().values(
                    run_id=current.run_id,
                    attempt_number=current.attempt,
                    fencing_token=current.token,
                    owner=current.owner,
                    started_at=now,
                    outcome="running",
                )
            )
            return current


def owned(current: Claim) -> Any:
    return sa.and_(
        jobs.c.run_id == current.run_id,
        jobs.c.state == "running",
        jobs.c.owner == current.owner,
        jobs.c.fencing_token == current.token,
        jobs.c.lease_until > sa.func.clock_timestamp(),
    )


def fence(connection: Connection, current: Claim) -> None:
    if (
        current.lost.is_set()
        or connection.execute(
            sa.select(jobs.c.run_id).where(owned(current)).with_for_update()
        ).first()
        is None
    ):
        raise ResearchError("Memo ownership lost", 409)


def heartbeat(engine: Engine, current: Claim) -> bool:
    if current.lost.is_set():
        return False
    with engine.begin() as connection:
        research.bounded(connection)
        return (
            connection.execute(
                jobs.update()
                .where(owned(current))
                .values(
                    lease_until=sa.func.clock_timestamp() + timedelta(seconds=60),
                    updated_at=sa.func.clock_timestamp(),
                )
            ).rowcount
            == 1
        )


def pin(engine: Engine, current: Claim, execution: dict[str, Any]) -> None:
    with engine.begin() as connection:
        research.bounded(connection)
        fence(connection, current)
        row = connection.execute(sa.select(jobs).where(owned(current))).mappings().one()
        if row["execution_sha256"] is not None and row["execution_sha256"] != digest(execution):
            raise ResearchError("Memo execution fingerprint mismatch", 409)
        connection.execute(
            jobs.update()
            .where(owned(current))
            .values(execution=canonical(execution).decode(), execution_sha256=digest(execution))
        )


def reserve_call(engine: Engine, current: Claim) -> None:
    with engine.begin() as connection:
        research.bounded(connection)
        fence(connection, current)
        if (
            connection.execute(
                jobs.update()
                .where(owned(current), jobs.c.model_calls < 2)
                .values(model_calls=jobs.c.model_calls + 1)
            ).rowcount
            != 1
        ):
            raise ResearchError("Memo model call budget exhausted")


def checkpoint(
    engine: Engine, current: Claim, draft: dict[str, Any] | None, provenance: dict[str, Any]
) -> None:
    with engine.begin() as connection:
        research.bounded(connection)
        fence(connection, current)
        if (
            connection.execute(
                jobs.update()
                .where(owned(current))
                .values(
                    draft=canonical(draft).decode() if draft is not None else None,
                    provenance=canonical(provenance).decode(),
                    updated_at=sa.func.clock_timestamp(),
                )
            ).rowcount
            != 1
        ):
            raise ResearchError("Memo ownership lost", 409)


def finish(connection: Connection, current: Claim, memo_hash: str) -> None:
    fence(connection, current)
    if (
        connection.execute(
            jobs.update()
            .where(owned(current))
            .values(
                state="ready",
                owner=None,
                lease_until=None,
                result_sha256=memo_hash,
                updated_at=sa.func.clock_timestamp(),
            )
        ).rowcount
        != 1
    ):
        raise ResearchError("Memo ownership lost", 409)
    connection.execute(
        attempts.update()
        .where(
            attempts.c.run_id == current.run_id,
            attempts.c.attempt_number == current.attempt,
            attempts.c.fencing_token == current.token,
            attempts.c.owner == current.owner,
        )
        .values(outcome="ready", ended_at=sa.func.clock_timestamp())
    )


def fail(engine: Engine, current: Claim, transient: bool = False) -> None:
    with engine.begin() as connection:
        research.bounded(connection)
        fence(connection, current)
        row = connection.execute(sa.select(jobs).where(owned(current))).mappings().one()
        retry = (
            transient
            and current.attempt < 3
            and (row["model_calls"] < 2 or row["draft"] is not None)
        )
        message = "Transient memo execution failure" if transient else "Memo execution failed"
        if (
            connection.execute(
                jobs.update()
                .where(owned(current))
                .values(
                    state="retry_wait" if retry else "failed",
                    owner=None,
                    lease_until=None,
                    error=message,
                    eligible_at=sa.func.clock_timestamp()
                    + timedelta(seconds=10 if current.attempt == 1 else 30),
                    updated_at=sa.func.clock_timestamp(),
                )
            ).rowcount
            != 1
        ):
            raise ResearchError("Memo ownership lost", 409)
        connection.execute(
            attempts.update()
            .where(
                attempts.c.run_id == current.run_id, attempts.c.attempt_number == current.attempt
            )
            .values(
                outcome="transient" if transient else "permanent",
                error=message,
                ended_at=sa.func.clock_timestamp(),
            )
        )


def inspect(engine: Engine, run_id: str) -> dict[str, Any]:
    identity(run_id)
    with engine.connect() as connection:
        row = (
            connection.execute(sa.select(jobs).where(jobs.c.run_id == run_id))
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise ResearchError("Memo job not found", 404)
        result = dict(row)
        result["attempts"] = [
            dict(r)
            for r in connection.execute(
                sa.select(attempts)
                .where(attempts.c.run_id == run_id)
                .order_by(attempts.c.attempt_number)
            ).mappings()
        ]
    for name in ("execution", "draft", "provenance"):
        if result[name] is not None:
            result[name] = json.loads(result[name])
    result["schema"] = "memo-status-v1"
    result["status"] = {"queued": "pending", "retry_wait": "pending"}.get(
        result["state"], result["state"]
    )
    return result
