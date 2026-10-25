"""Database-time fenced copilot execution and atomic research handoff."""

import json
import threading
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine

from marketlab.analytics.cache import canonical
from marketlab.research import store as research
from marketlab.research.spec import ResearchError

from .spec import digest, identity, key

metadata = sa.MetaData()
requests = sa.Table(
    "copilot_requests",
    metadata,
    sa.Column("request_id", sa.String(36), primary_key=True),
    sa.Column("idempotency_key", sa.String(128)),
    sa.Column("request_sha256", sa.String(64)),
    sa.Column("body", sa.Text),
    sa.Column("current_revision", sa.Integer),
    sa.Column("run_id", sa.String(36)),
    sa.Column("created_at", sa.DateTime(timezone=True)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
)
revisions = sa.Table(
    "copilot_revisions",
    metadata,
    sa.Column("request_id", sa.String(36), primary_key=True),
    sa.Column("revision", sa.Integer, primary_key=True),
    sa.Column("body", sa.Text),
    sa.Column("body_sha256", sa.String(64)),
    sa.Column("answer_key", sa.String(128)),
    sa.Column("outcome", sa.String(24)),
    sa.Column("interpretation", sa.Text),
    sa.Column("provenance", sa.Text),
    sa.Column("questions", sa.Text),
    sa.Column("spec", sa.Text),
    sa.Column("created_at", sa.DateTime(timezone=True)),
)
jobs = sa.Table(
    "copilot_jobs",
    metadata,
    sa.Column("job_id", sa.String(36), primary_key=True),
    sa.Column("request_id", sa.String(36)),
    sa.Column("revision", sa.Integer),
    sa.Column("state", sa.String(16)),
    sa.Column("attempt_count", sa.Integer),
    sa.Column("model_calls", sa.Integer),
    sa.Column("fencing_token", sa.BigInteger),
    sa.Column("owner", sa.String(36)),
    sa.Column("lease_until", sa.DateTime(timezone=True)),
    sa.Column("eligible_at", sa.DateTime(timezone=True)),
    sa.Column("error", sa.String(160)),
    sa.Column("created_at", sa.DateTime(timezone=True)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
)
attempts = sa.Table(
    "copilot_attempts",
    metadata,
    sa.Column("job_id", sa.String(36), primary_key=True),
    sa.Column("attempt_number", sa.Integer, primary_key=True),
    sa.Column("fencing_token", sa.BigInteger),
    sa.Column("owner", sa.String(36)),
    sa.Column("started_at", sa.DateTime(timezone=True)),
    sa.Column("ended_at", sa.DateTime(timezone=True)),
    sa.Column("outcome", sa.String(16)),
    sa.Column("error", sa.String(160)),
)


@dataclass(frozen=True)
class Claim:
    job_id: str
    request_id: str
    revision: int
    owner: str
    token: int
    attempt: int
    lost: threading.Event = field(default_factory=threading.Event, compare=False)


def revision_where(request_id: str, revision: int) -> Any:
    return sa.and_(revisions.c.request_id == request_id, revisions.c.revision == revision)


def enqueue(
    connection: Connection,
    request_id: str,
    revision: int,
    body: dict[str, Any],
    answer_key: str | None = None,
) -> None:
    now = sa.func.clock_timestamp()
    connection.execute(
        revisions.insert().values(
            request_id=request_id,
            revision=revision,
            body=canonical(body).decode(),
            body_sha256=digest(body),
            answer_key=answer_key,
            created_at=now,
        )
    )
    connection.execute(
        jobs.insert().values(
            job_id=str(uuid4()),
            request_id=request_id,
            revision=revision,
            state="queued",
            attempt_count=0,
            model_calls=0,
            fencing_token=0,
            eligible_at=now,
            created_at=now,
            updated_at=now,
        )
    )


def create(engine: Engine, body: dict[str, Any], idempotency_key: str) -> tuple[str, int, bool]:
    key(idempotency_key)
    with engine.begin() as connection:
        research.bounded(connection)
        research.advisory(connection, "copilot-create:" + idempotency_key)
        row = (
            connection.execute(
                sa.select(requests).where(requests.c.idempotency_key == idempotency_key)
            )
            .mappings()
            .one_or_none()
        )
        if row:
            if row["request_sha256"] != digest(body):
                raise ResearchError("Copilot idempotency key conflict", 409)
            return row["request_id"], row["current_revision"], True
        request_id = str(uuid4())
        connection.execute(
            requests.insert().values(
                request_id=request_id,
                idempotency_key=idempotency_key,
                request_sha256=digest(body),
                body=canonical(body).decode(),
                current_revision=0,
                created_at=sa.func.clock_timestamp(),
                updated_at=sa.func.clock_timestamp(),
            )
        )
        enqueue(connection, request_id, 0, body)
        return request_id, 0, False


def answer(
    engine: Engine, request_id: str, body: dict[str, Any], answer_key: str
) -> tuple[str, int, bool]:
    identity(request_id)
    key(answer_key)
    with engine.begin() as connection:
        research.bounded(connection)
        row = (
            connection.execute(
                sa.select(requests).where(requests.c.request_id == request_id).with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise ResearchError("Copilot request not found", 404)
        previous = (
            connection.execute(
                sa.select(revisions).where(
                    revisions.c.request_id == request_id, revisions.c.answer_key == answer_key
                )
            )
            .mappings()
            .one_or_none()
        )
        if previous:
            if previous["body_sha256"] != digest(body):
                raise ResearchError("Copilot answer key conflict", 409)
            return request_id, previous["revision"], True
        current = (
            connection.execute(
                sa.select(revisions).where(revision_where(request_id, row["current_revision"]))
            )
            .mappings()
            .one()
        )
        if (
            body["expected_revision"] != row["current_revision"]
            or row["current_revision"] >= 5
            or current["outcome"] != "needs_clarification"
            or row["run_id"] is not None
        ):
            raise ResearchError("Copilot clarification state conflict", 409)
        revision = row["current_revision"] + 1
        enqueue(connection, request_id, revision, body, answer_key)
        connection.execute(
            requests.update()
            .where(requests.c.request_id == request_id)
            .values(current_revision=revision, updated_at=sa.func.clock_timestamp())
        )
        return request_id, revision, False


def claim(engine: Engine, request_id: str | None = None) -> Claim | None:
    if request_id is not None:
        identity(request_id)
    with engine.begin() as connection:
        research.bounded(connection)
        now = sa.func.clock_timestamp()
        query = sa.select(jobs).where(
            sa.or_(
                jobs.c.state == "queued",
                sa.and_(jobs.c.state == "retry_wait", jobs.c.eligible_at <= now),
                sa.and_(jobs.c.state == "running", jobs.c.lease_until <= now),
            )
        )
        if request_id:
            query = query.where(jobs.c.request_id == request_id)
        while True:
            row = (
                connection.execute(
                    query.order_by(jobs.c.created_at, jobs.c.job_id)
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
                    .values(outcome="expired", ended_at=now)
                )
            if row["attempt_count"] >= 3:
                connection.execute(
                    jobs.update()
                    .where(jobs.c.job_id == row["job_id"])
                    .values(
                        state="failed",
                        owner=None,
                        lease_until=None,
                        error="Copilot attempt budget exhausted",
                        updated_at=now,
                    )
                )
                connection.execute(
                    revisions.update()
                    .where(revision_where(row["request_id"], row["revision"]))
                    .values(outcome="failed")
                )
                continue
            current = Claim(
                row["job_id"],
                row["request_id"],
                row["revision"],
                str(uuid4()),
                row["fencing_token"] + 1,
                row["attempt_count"] + 1,
            )
            connection.execute(
                jobs.update()
                .where(jobs.c.job_id == current.job_id)
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
                    job_id=current.job_id,
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
        jobs.c.job_id == current.job_id,
        jobs.c.state == "running",
        jobs.c.owner == current.owner,
        jobs.c.fencing_token == current.token,
        jobs.c.lease_until > sa.func.clock_timestamp(),
    )


def fence(connection: Connection, current: Claim) -> None:
    if (
        current.lost.is_set()
        or connection.execute(
            sa.select(jobs.c.job_id).where(owned(current)).with_for_update()
        ).first()
        is None
    ):
        raise ResearchError("Copilot ownership lost", 409)
    row = (
        connection.execute(
            sa.select(requests).where(requests.c.request_id == current.request_id).with_for_update()
        )
        .mappings()
        .one()
    )
    if row["current_revision"] != current.revision or row["run_id"] is not None:
        raise ResearchError("Copilot revision ownership lost", 409)


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
            raise ResearchError("Copilot model call budget exhausted")


def checkpoint(
    engine: Engine, current: Claim, value: dict[str, Any] | None, provenance: dict[str, Any]
) -> None:
    with engine.begin() as connection:
        research.bounded(connection)
        fence(connection, current)
        connection.execute(
            revisions.update()
            .where(revision_where(current.request_id, current.revision))
            .values(
                interpretation=canonical(value).decode() if value is not None else None,
                provenance=canonical(provenance).decode(),
            )
        )
        if (
            connection.execute(
                jobs.update().where(owned(current)).values(updated_at=sa.func.clock_timestamp())
            ).rowcount
            != 1
        ):
            raise ResearchError("Copilot ownership lost", 409)


def complete(
    connection: Connection,
    current: Claim,
    outcome: str,
    questions: list[dict[str, str]],
    spec: dict[str, Any] | None = None,
    fingerprint: dict[str, Any] | None = None,
) -> str | None:
    research.bounded(connection)
    fence(connection, current)
    run_id = None
    if outcome == "submitted":
        assert spec is not None and fingerprint is not None
        run_id, replayed = research.register(
            connection, "copilot." + current.request_id, spec, fingerprint
        )
        # A public manual idempotency key may collide; never adopt an unrelated run.
        if replayed:
            raise ResearchError("Copilot research key conflict", 409)
    if (
        connection.execute(
            jobs.update()
            .where(owned(current))
            .values(
                state="completed",
                owner=None,
                lease_until=None,
                updated_at=sa.func.clock_timestamp(),
            )
        ).rowcount
        != 1
    ):
        raise ResearchError("Copilot ownership lost", 409)
    connection.execute(
        requests.update()
        .where(requests.c.request_id == current.request_id)
        .values(run_id=run_id, updated_at=sa.func.clock_timestamp())
    )
    connection.execute(
        revisions.update()
        .where(revision_where(current.request_id, current.revision))
        .values(
            outcome=outcome,
            questions=canonical(questions).decode(),
            spec=canonical(spec).decode() if spec is not None else None,
        )
    )
    connection.execute(
        attempts.update()
        .where(
            attempts.c.job_id == current.job_id,
            attempts.c.attempt_number == current.attempt,
            attempts.c.fencing_token == current.token,
            attempts.c.owner == current.owner,
        )
        .values(outcome="completed", ended_at=sa.func.clock_timestamp())
    )
    return run_id


def finish(
    engine: Engine,
    current: Claim,
    outcome: str,
    questions: list[dict[str, str]],
    spec: dict[str, Any] | None = None,
    fingerprint: dict[str, Any] | None = None,
) -> str | None:
    with engine.begin() as connection:
        return complete(connection, current, outcome, questions, spec, fingerprint)


def fail(engine: Engine, current: Claim, transient: bool = False) -> None:
    with engine.begin() as connection:
        research.bounded(connection)
        fence(connection, current)
        retry = transient and current.attempt < 3
        message = "Transient copilot execution failure" if transient else "Copilot execution failed"
        result = connection.execute(
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
        )
        if result.rowcount != 1:
            raise ResearchError("Copilot ownership lost", 409)
        connection.execute(
            attempts.update()
            .where(
                attempts.c.job_id == current.job_id, attempts.c.attempt_number == current.attempt
            )
            .values(
                outcome="transient" if transient else "permanent",
                error=message,
                ended_at=sa.func.clock_timestamp(),
            )
        )
        if not retry:
            connection.execute(
                revisions.update()
                .where(revision_where(current.request_id, current.revision))
                .values(outcome="failed")
            )


def inspect(engine: Engine, request_id: str) -> dict[str, Any]:
    identity(request_id)
    with engine.connect() as connection:
        row = (
            connection.execute(sa.select(requests).where(requests.c.request_id == request_id))
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise ResearchError("Copilot request not found", 404)
        history = [
            dict(r)
            for r in connection.execute(
                sa.select(
                    revisions,
                    jobs.c.job_id,
                    jobs.c.state,
                    jobs.c.attempt_count,
                    jobs.c.model_calls,
                    jobs.c.error,
                )
                .join(
                    jobs,
                    sa.and_(
                        jobs.c.request_id == revisions.c.request_id,
                        jobs.c.revision == revisions.c.revision,
                    ),
                )
                .where(revisions.c.request_id == request_id)
                .order_by(revisions.c.revision)
            ).mappings()
        ]
        for item in history:
            for name in ("body", "interpretation", "provenance", "questions", "spec"):
                item[name] = json.loads(item[name]) if item[name] is not None else None
            item["attempts"] = [
                dict(a)
                for a in connection.execute(
                    sa.select(attempts)
                    .where(attempts.c.job_id == item["job_id"])
                    .order_by(attempts.c.attempt_number)
                ).mappings()
            ]
    return {
        **dict(row),
        "body": json.loads(row["body"]),
        "revisions": history,
        "state": history[-1]["state"],
        "outcome": history[-1]["outcome"],
    }
