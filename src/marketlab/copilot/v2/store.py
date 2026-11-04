"""Append-only revisions and an atomic sole manual-service research handoff."""

from typing import Any
from uuid import uuid4

from sqlalchemy.engine import Engine

from marketlab.datasets.v2.common import V2Error, canonical_json, digest
from marketlab.datasets.v2.core import execute, lock, one, transaction, uid, wire
from marketlab.research.v2 import store as research
from marketlab.research.v2.spec import ResearchSpec

from . import durable


def replay(engine: Engine, body: dict[str, Any], key: str) -> tuple[str, int, bool] | None:
    research.key_value(key)
    with engine.connect() as connection:
        row = one(
            connection, "SELECT * FROM v2_copilot_requests WHERE idempotency_key=:key", key=key
        )
    if row is None:
        return None
    if row["request_sha256"] != digest(body):
        raise V2Error("revision_conflict", "Copilot operation key conflict")
    return str(row["request_id"]), row["current_revision"], True


def revision(
    connection: Any, request_id: str, number: int, body: dict[str, Any], key: str | None = None
) -> None:
    execute(
        connection,
        "INSERT INTO v2_copilot_revisions "
        "(request_id,revision,body_json,body_sha256,answer_key) VALUES "
        "(:id,:revision,:body,:sha,:key)",
        id=request_id,
        revision=number,
        body=canonical_json(body).decode(),
        sha=digest(body),
        key=key,
    )
    execute(
        connection,
        "INSERT INTO v2_copilot_jobs (job_id,request_id,revision) VALUES (:job,:id,:revision)",
        job=str(uuid4()),
        id=request_id,
        revision=number,
    )


def create(
    engine: Engine,
    body: dict[str, Any],
    snapshot: dict[str, Any],
    execution: dict[str, Any],
    key: str,
) -> tuple[str, int, bool]:
    research.key_value(key)
    with transaction(engine) as connection:
        lock(connection, "v2-copilot-create:" + key)
        row = one(
            connection, "SELECT * FROM v2_copilot_requests WHERE idempotency_key=:key", key=key
        )
        if row:
            if row["request_sha256"] != digest(body):
                raise V2Error("revision_conflict", "Copilot operation key conflict")
            return str(row["request_id"]), row["current_revision"], True
        identity = str(uuid4())
        execute(
            connection,
            "INSERT INTO v2_copilot_requests "
            "(request_id,idempotency_key,request_sha256,body_json,snapshot_json,"
            "snapshot_sha256,execution_json,execution_sha256,lock_sha256) VALUES "
            "(:id,:key,:request,:body,:snapshot,:snapshot_sha,:execution,:execution_sha,:lock)",
            id=identity,
            key=key,
            request=digest(body),
            body=canonical_json(body).decode(),
            snapshot=canonical_json(snapshot).decode(),
            snapshot_sha=digest(snapshot),
            execution=canonical_json(execution).decode(),
            execution_sha=digest(execution),
            lock=execution["lock_sha256"],
        )
        revision(connection, identity, 0, body)
        return identity, 0, False


def answer(
    engine: Engine, request_id: str, body: dict[str, Any], key: str
) -> tuple[str, int, bool]:
    uid(request_id)
    research.key_value(key)
    with transaction(engine) as connection:
        row = one(
            connection,
            "SELECT * FROM v2_copilot_requests WHERE request_id=:id FOR UPDATE",
            id=request_id,
        )
        if row is None:
            raise V2Error("not_found", "Copilot request not found")
        old = one(
            connection,
            "SELECT * FROM v2_copilot_revisions WHERE request_id=:id AND answer_key=:key",
            id=request_id,
            key=key,
        )
        if old is not None:
            if old["body_sha256"] != digest(body):
                raise V2Error("revision_conflict", "Clarification operation key conflict")
            return request_id, old["revision"], True
        current = one(
            connection,
            "SELECT * FROM v2_copilot_revisions WHERE request_id=:id AND revision=:revision",
            id=request_id,
            revision=row["current_revision"],
        )
        if (
            current is None
            or row["current_revision"] != body["expected_revision"]
            or row["current_revision"] >= 5
            or current["outcome"] != "needs_clarification"
            or row["run_id"] is not None
        ):
            raise V2Error("revision_conflict", "Clarification revision conflict")
        number = row["current_revision"] + 1
        revision(connection, request_id, number, body, key)
        execute(
            connection,
            "UPDATE v2_copilot_requests SET "
            "current_revision=:revision,updated_at=clock_timestamp() WHERE request_id=:id",
            revision=number,
            id=request_id,
        )
        return request_id, number, False


def inspect(engine: Engine, request_id: str) -> dict[str, Any]:
    uid(request_id)
    with engine.connect() as connection:
        # Read the request, revisions and calls from the same committed snapshot.
        connection.execution_options(isolation_level="REPEATABLE READ")
        row = one(
            connection, "SELECT * FROM v2_copilot_requests WHERE request_id=:id", id=request_id
        )
        if row is None:
            raise V2Error("not_found", "Copilot request not found")
        result = durable.decoded(row, ("body", "snapshot", "execution"))
        if any(
            digest(result[k]) != result[h]
            for k, h in (
                ("body", "request_sha256"),
                ("snapshot", "snapshot_sha256"),
                ("execution", "execution_sha256"),
            )
        ):
            raise V2Error("integrity_failure", "Copilot stored identity mismatch")
        history = []
        for revision in execute(
            connection,
            "SELECT r.*,j.job_id,j.state,j.attempt_count,j.model_calls,j.error_code FROM "
            "v2_copilot_revisions r JOIN v2_copilot_jobs j USING(request_id,revision) WHERE "
            "request_id=:id ORDER BY revision",
            id=request_id,
        ).mappings():
            item = durable.decoded(
                dict(revision), ("body", "interpretation", "provenance", "questions", "spec")
            )
            if digest(item["body"]) != item["body_sha256"] or (
                item["spec"] is not None and digest(item["spec"]) != item["spec_sha256"]
            ):
                raise V2Error("integrity_failure", "Copilot revision integrity failure")
            item["calls"] = [
                dict(c)
                for c in execute(
                    connection,
                    "SELECT "
                    "call_number,attempt_number,state,model_digest,input_sha256,"
                    "response_sha256,reserved_at,finished_at FROM v2_copilot_calls WHERE "
                    "job_id=:id ORDER BY call_number",
                    id=item["job_id"],
                ).mappings()
            ]
            history.append(item)
    if len(history) != result["current_revision"] + 1:
        raise V2Error("integrity_failure", "Copilot revision history incomplete")
    result = wire(
        {
            **result,
            "schema": "copilot-status-v2",
            "revisions": history,
            "state": history[-1]["state"],
            "outcome": history[-1]["outcome"],
        }
    )
    return dict(result)


def finish(
    engine: Engine,
    current: durable.Claim,
    outcome: str,
    questions: list[dict[str, str]],
    spec: ResearchSpec | None = None,
    fingerprint: dict[str, Any] | None = None,
    rows: list[dict[str, Any]] | None = None,
) -> str | None:
    with transaction(engine) as connection:
        durable.fence(connection, current)
        run = None
        if outcome == "submitted":
            if spec is None or fingerprint is None or rows is None:
                raise V2Error("integrity_failure", "Missing validated handoff")
            run, replayed = research.register(
                connection, "copilot-v2." + str(current.request_id), spec, fingerprint, rows
            )
            if replayed:
                raise V2Error("revision_conflict", "Reserved handoff key already belongs to work")
        durable.complete(connection, current)
        execute(
            connection,
            "UPDATE v2_copilot_revisions SET "
            "outcome=:outcome,questions_json=:questions,spec_json=:spec,spec_sha256=:sha WHERE "
            "request_id=:id AND revision=:revision",
            outcome=outcome,
            questions=canonical_json(questions).decode(),
            spec=canonical_json(spec.body()).decode() if spec else None,
            sha=spec.digest if spec else None,
            id=current.request_id,
            revision=current.revision,
        )
        execute(
            connection,
            "UPDATE v2_copilot_requests SET run_id=:run,updated_at=clock_timestamp() WHERE "
            "request_id=:id",
            run=run,
            id=current.request_id,
        )
        return run
