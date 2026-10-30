"""Isolated research records, DB-time ownership, cancellation and immutable success."""

import json
import threading
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from sqlalchemy.engine import Connection, Engine

from marketlab.datasets.v2.common import KEY, V2Error, canonical_json, digest
from marketlab.datasets.v2.core import execute, lock, one, transaction, uid, wire

from .spec import SCHEMA, ResearchSpec


@dataclass(frozen=True)
class Claim:
    run_id: str
    owner: str
    token: int
    attempt: int
    lost: threading.Event = field(default_factory=threading.Event, compare=False)


def key_value(key: str) -> None:
    if not isinstance(key, str) or KEY.fullmatch(key) is None:
        raise V2Error("invalid_request", "Invalid research operation key")


def replay(engine: Engine, key: str, request_hash: str) -> str | None:
    key_value(key)
    with engine.connect() as connection:
        row = one(
            connection,
            "SELECT s.request_sha256,r.run_id FROM v2_research_submissions s "
            "JOIN v2_research_runs r USING(submission_id) WHERE idempotency_key=:key",
            key=key,
        )
    if row is None:
        return None
    if row["request_sha256"] != request_hash:
        raise V2Error("revision_conflict", "Research operation key conflict")
    return str(row["run_id"])


def submit(
    engine: Engine,
    key: str,
    spec: ResearchSpec,
    fingerprint: dict[str, Any],
    rows: list[dict[str, Any]],
) -> tuple[str, bool]:
    key_value(key)
    if not 1 <= len(rows) <= 62:
        raise V2Error("invalid_request", "Invalid prepared research selection")
    sid, rid = uuid4(), uuid4()
    with transaction(engine) as connection:
        lock(connection, "v2-research-submit:" + key)
        old = one(
            connection,
            "SELECT s.request_sha256,r.run_id FROM v2_research_submissions s "
            "JOIN v2_research_runs r USING(submission_id) WHERE idempotency_key=:key",
            key=key,
        )
        if old:
            if old["request_sha256"] != spec.digest:
                raise V2Error("revision_conflict", "Research operation key conflict")
            return str(old["run_id"]), True
        execution = fingerprint["execution"]
        execute(
            connection,
            "INSERT INTO v2_research_submissions VALUES "
            "(:id,:key,:request,:spec,:contract,:fingerprint,:fingerprint_hash,:execution,:lock,"
            "clock_timestamp())",
            id=sid,
            key=key,
            request=spec.digest,
            spec=canonical_json(spec.body()).decode(),
            contract=SCHEMA,
            fingerprint=canonical_json(fingerprint).decode(),
            fingerprint_hash=digest(fingerprint),
            execution=execution["source_sha256"],
            lock=execution["lock_sha256"],
        )
        for row in rows:
            metadata = fingerprint["instruments"][row["instrument_id"]]
            execute(
                connection,
                "INSERT INTO v2_research_selections VALUES "
                "(:submission,:instrument,:semantic,:day,:version,:legacy,:v2,:manifest,:metadata)",
                submission=sid,
                instrument=row["instrument_id"],
                semantic=row["semantic_sha256"],
                day=row["trade_date"],
                version=row["dataset_version_id"],
                legacy=row["dataset_version_id"]
                if row["contract"] == "dataset-manifest-v1"
                else None,
                v2=row["dataset_version_id"] if row["contract"] == "dataset-manifest-v2" else None,
                manifest=row["manifest_sha256"],
                metadata=canonical_json(metadata).decode(),
            )
        execute(
            connection,
            "INSERT INTO v2_research_runs VALUES "
            "(:id,:submission,'queued',0,0,0,NULL,NULL,clock_timestamp(),false,NULL,NULL,"
            "clock_timestamp(),clock_timestamp())",
            id=rid,
            submission=sid,
        )
    return str(rid), False


def inspect(engine: Engine, run_id: str) -> dict[str, Any]:
    identity = uid(run_id)
    with engine.connect() as connection:
        row = one(
            connection,
            "SELECT r.*,s.spec_json,s.fingerprint_json,s.fingerprint_sha256,"
            "s.execution_sha256 FROM v2_research_runs r JOIN v2_research_submissions s "
            "USING(submission_id) WHERE run_id=:id",
            id=identity,
        )
        if row is None:
            raise V2Error("not_found", "Research run not found")
        attempts = [
            dict(v)
            for v in execute(
                connection,
                "SELECT * FROM v2_research_attempts WHERE run_id=:id ORDER BY attempt_number",
                id=identity,
            ).mappings()
        ]
    row["spec"] = json.loads(row.pop("spec_json"))
    row["fingerprint"] = json.loads(row.pop("fingerprint_json"))
    if digest(row["fingerprint"]) != row.pop("fingerprint_sha256"):
        raise V2Error("integrity_failure", "Research provenance integrity failure")
    row.update(
        attempts=attempts,
        numerical_available=row["state"] == "succeeded",
        memo_available=False,
        memo_contract="unsupported",
    )
    return wire(row)  # type: ignore[no-any-return]


def claim(engine: Engine, execution: dict[str, Any], run_id: str | None = None) -> Claim | None:
    identity = None if run_id is None else uid(run_id)
    with transaction(engine) as connection:
        while True:
            row = one(
                connection,
                "SELECT r.* FROM v2_research_runs r JOIN v2_research_submissions s "
                "USING(submission_id) WHERE s.execution_sha256=:execution AND "
                "s.lock_sha256=:lock AND s.contract=:contract AND "
                "s.fingerprint_json::jsonb->'execution'->>'schema'=:contract AND "
                "s.fingerprint_json::jsonb->'execution'->>'numerics'=:numerics AND "
                "s.fingerprint_json::jsonb->'execution'->>'bars'=:bars AND "
                "s.fingerprint_json::jsonb->'execution'->>'inventory'=:inventory AND "
                "(CAST(:id AS uuid) IS NULL OR r.run_id=:id) AND "
                "(r.state='queued' OR (r.state='retry_wait' AND r.eligible_at<=clock_timestamp()) "
                "OR (r.state='running' AND r.lease_until<=clock_timestamp())) "
                "ORDER BY r.created_at,r.run_id LIMIT 1 FOR UPDATE OF r SKIP LOCKED",
                execution=execution["source_sha256"],
                lock=execution["lock_sha256"],
                contract=SCHEMA,
                numerics=execution["numerics"],
                bars=execution["bars"],
                inventory=execution["inventory"],
                id=identity,
            )
            if row is None:
                return None
            if row["state"] == "running":
                execute(
                    connection,
                    "UPDATE v2_research_attempts SET outcome='expired',"
                    "ended_at=clock_timestamp() WHERE run_id=:id AND attempt_number=:attempt "
                    "AND outcome='running'",
                    id=row["run_id"],
                    attempt=row["attempt_count"],
                )
            if row["cancel_requested"] or row["attempt_count"] >= 3:
                state = "cancelled" if row["cancel_requested"] else "failed"
                execute(
                    connection,
                    "UPDATE v2_research_runs SET state=:state,owner=NULL,lease_until=NULL,"
                    "revision=revision+1,error_code=:error,updated_at=clock_timestamp() "
                    "WHERE run_id=:id",
                    state=state,
                    error="cancelled" if state == "cancelled" else "execution_failed",
                    id=row["run_id"],
                )
                continue
            current = Claim(
                str(row["run_id"]), str(uuid4()), row["fencing_token"] + 1, row["attempt_count"] + 1
            )
            execute(
                connection,
                "UPDATE v2_research_runs SET state='running',revision=revision+1,"
                "attempt_count=:attempt,fencing_token=:token,owner=:owner,"
                "lease_until=clock_timestamp()+interval '60 seconds',updated_at=clock_timestamp(),"
                "error_code=NULL WHERE run_id=:id",
                id=current.run_id,
                owner=current.owner,
                token=current.token,
                attempt=current.attempt,
            )
            execute(
                connection,
                "INSERT INTO v2_research_attempts VALUES "
                "(:id,:attempt,:token,:owner,clock_timestamp(),NULL,'running',NULL)",
                id=current.run_id,
                attempt=current.attempt,
                token=current.token,
                owner=current.owner,
            )
            return current


def fence(connection: Connection, current: Claim, *, allow_cancel: bool = False) -> dict[str, Any]:
    row = one(
        connection, "SELECT * FROM v2_research_runs WHERE run_id=:id FOR UPDATE", id=current.run_id
    )
    if (
        row is None
        or row["state"] != "running"
        or str(row["owner"]) != current.owner
        or (row["fencing_token"] != current.token)
    ):
        raise V2Error("revision_conflict", "Research ownership lost")
    alive = execute(
        connection, "SELECT :lease > clock_timestamp()", lease=row["lease_until"]
    ).scalar_one()
    if not alive:
        raise V2Error("revision_conflict", "Research ownership lost")
    if row["cancel_requested"] and not allow_cancel:
        raise V2Error("cancelled", "Research cancellation requested")
    return row


def heartbeat(engine: Engine, current: Claim) -> bool:
    with transaction(engine) as connection:
        row = one(
            connection,
            "UPDATE v2_research_runs SET lease_until=clock_timestamp()+interval '60 seconds' "
            "WHERE run_id=:id AND state='running' AND owner=:owner AND fencing_token=:token "
            "AND lease_until>clock_timestamp() RETURNING cancel_requested",
            id=current.run_id,
            owner=current.owner,
            token=current.token,
        )
        if row and row["cancel_requested"]:
            current.lost.set()
        return row is not None


def finish(
    connection: Connection, current: Claim, *, state: str = "succeeded", error: str | None = None
) -> None:
    row = fence(connection, current, allow_cancel=state != "succeeded")
    if row["cancel_requested"]:
        state, error = "cancelled", "cancelled"
    outcome = {"failed": "permanent", "retry_wait": "transient"}.get(state, state)
    execute(
        connection,
        "UPDATE v2_research_attempts SET outcome=:outcome,error_code=:error,"
        "ended_at=clock_timestamp() WHERE run_id=:id AND attempt_number=:attempt",
        outcome=outcome,
        error=error,
        id=current.run_id,
        attempt=current.attempt,
    )
    execute(
        connection,
        "UPDATE v2_research_runs SET state=:state,owner=NULL,lease_until=NULL,"
        "revision=revision+1,result_id=:result,error_code=:error,"
        "eligible_at=clock_timestamp()+make_interval(secs=>:delay),updated_at=clock_timestamp() "
        "WHERE run_id=:id",
        state=state,
        result=current.run_id if state == "succeeded" else None,
        error=error,
        delay=10 if current.attempt == 1 else 30,
        id=current.run_id,
    )


def fail(engine: Engine, current: Claim, code: str, transient: bool) -> None:
    with transaction(engine) as connection:
        finish(
            connection,
            current,
            state="retry_wait" if transient and current.attempt < 3 else "failed",
            error=code,
        )


def cancel(engine: Engine, run_id: str, revision: int, key: str) -> dict[str, Any]:
    key_value(key)
    identity = uid(run_id)
    if type(revision) is not int or revision < 0:
        raise V2Error("invalid_request", "Invalid expected research revision")
    request = digest({"run_id": run_id, "expected_revision": revision})
    with transaction(engine) as connection:
        row = one(
            connection, "SELECT * FROM v2_research_runs WHERE run_id=:id FOR UPDATE", id=identity
        )
        if row is None:
            raise V2Error("not_found", "Research run not found")
        lock(connection, "v2-research-cancel:" + key)
        old = one(
            connection,
            "SELECT * FROM v2_research_operations WHERE operation='cancel' "
            "AND protocol=:protocol AND idempotency_key=:key",
            protocol=SCHEMA,
            key=key,
        )
        if old:
            if old["request_sha256"] != request:
                raise V2Error("revision_conflict", "Research operation key conflict")
            return json.loads(old["response_json"])  # type: ignore[no-any-return]
        if row["revision"] != revision or row["state"] in {"succeeded", "failed"}:
            raise V2Error("revision_conflict", "Research cancellation conflict")
        if row["state"] != "cancelled":
            execute(
                connection,
                "UPDATE v2_research_runs SET cancel_requested=true,revision=revision+1,"
                "state=CASE WHEN state='running' THEN state ELSE 'cancelled' END,"
                "updated_at=clock_timestamp() WHERE run_id=:id",
                id=identity,
            )
        result = {
            "id": run_id,
            "state": "running" if row["state"] == "running" else "cancelled",
            "revision": row["revision"] + (row["state"] != "cancelled"),
            "cancel_requested": True,
        }
        execute(
            connection,
            "INSERT INTO v2_research_operations VALUES "
            "('cancel',:protocol,:key,:hash,:run,:response,clock_timestamp())",
            protocol=SCHEMA,
            key=key,
            hash=request,
            run=identity,
            response=canonical_json(result).decode(),
        )
        return result
