"""Database-time v2 claims, fencing, retries and cancellation."""

from datetime import timedelta
from typing import Any, cast
from uuid import uuid4

from sqlalchemy.engine import Connection, Engine

from .common import V2Error, canonical_json, digest
from .core import (
    PROTOCOL,
    TRANSFORM,
    execute,
    execution_identity,
    instrument,
    official_request,
    one,
    operation,
    save_operation,
    transaction,
    uid,
    wire,
)


def create_submission(
    connection: Connection,
    request: dict[str, Any],
    identities: list[str],
    first: Any,
    before: Any,
    *,
    import_id: Any = None,
) -> tuple[Any, list[Any]]:
    sid = uuid4()
    fingerprint = execution_identity()
    execute(
        connection,
        "INSERT INTO v2_ingestion_submissions VALUES (:id,:sha,CAST(:request AS jsonb),"
        ":contract,:execution,:lock,:transform,:first,:before,:count,:children,clock_timestamp())",
        id=sid,
        sha=digest(request),
        request=canonical_json(request).decode(),
        contract=PROTOCOL,
        execution=fingerprint["execution_sha256"],
        lock=fingerprint["lock_sha256"],
        transform=TRANSFORM,
        first=first,
        before=before,
        count=len(identities),
        children=len(identities) * (before - first).days,
    )
    jobs = []
    for identity in identities:
        current = instrument(connection, identity, enabled=True)
        for offset in range((before - first).days):
            jid = uuid4()
            execute(
                connection,
                "INSERT INTO v2_ingestion_jobs (job_id,submission_id,instrument_id,semantic_sha256,"
                "instrument_snapshot,trade_date,source_mode,import_id,state,revision,attempt_count,"
                "fencing_token,eligible_at,cancel_requested,created_at,updated_at) VALUES "
                "(:job,:submission,:instrument,:semantic,CAST(:snapshot AS jsonb),:day,:mode,"
                ":import_id,'queued',0,0,0,clock_timestamp(),false,clock_timestamp(),clock_timestamp())",
                job=jid,
                submission=sid,
                instrument=identity,
                semantic=current["semantic_sha256"],
                snapshot=canonical_json(wire(current)).decode(),
                day=first + timedelta(days=offset),
                mode="official" if import_id is None else "canonical",
                import_id=import_id,
            )
            jobs.append(jid)
    count = execute(
        connection, "SELECT count(*) FROM v2_ingestion_jobs WHERE submission_id=:id", id=sid
    ).scalar_one()
    if count != len(identities) * (before - first).days or not 1 <= count <= 62:
        raise V2Error("integrity_failure", "Submission child set mismatch")
    return sid, jobs


def submit(engine: Engine, request: dict[str, Any], key: str) -> dict[str, Any]:
    identities, first, before = official_request(request)
    canonical = dict(request, instrument_ids=identities)
    with transaction(engine) as connection:
        replay = operation(connection, "submit", key, canonical)
        if replay is not None:
            return replay
        sid, jobs = create_submission(connection, canonical, identities, first, before)
        return save_operation(
            connection,
            "submit",
            key,
            canonical,
            {"submission_id": str(sid), "job_ids": list(map(str, jobs)), "child_count": len(jobs)},
        )


def project(connection: Connection, job: dict[str, Any], state: str, error: str | None) -> None:
    if job["import_id"] is not None:
        execute(
            connection,
            "UPDATE v2_canonical_imports SET state=:state,error_code=:error,revision=revision+1,"
            "updated_at=clock_timestamp() WHERE import_id=:id",
            state=state,
            error=error,
            id=job["import_id"],
        )


def lock_job(connection: Connection, job_id: Any) -> dict[str, Any]:
    # Read association without a job lock, then follow import -> job order.
    association = one(
        connection, "SELECT import_id FROM v2_ingestion_jobs WHERE job_id=:id", id=job_id
    )
    if association is None:
        raise V2Error("not_found", "Ingestion job not found")
    if association["import_id"] is not None:
        execute(
            connection,
            "SELECT import_id FROM v2_canonical_imports WHERE import_id=:id FOR UPDATE",
            id=association["import_id"],
        )
    result = one(
        connection, "SELECT * FROM v2_ingestion_jobs WHERE job_id=:id FOR UPDATE", id=job_id
    )
    if result is None:
        raise V2Error("not_found", "Ingestion job not found")
    return result


def finish(
    connection: Connection,
    job: dict[str, Any],
    state: str,
    outcome: str,
    error: str | None = None,
    *,
    version: str | None = None,
    delay: int = 0,
) -> None:
    execute(
        connection,
        "UPDATE v2_ingestion_jobs SET state=:state,owner=NULL,lease_until=NULL,"
        "result_version=:version,error_code=:error,revision=revision+1,"
        "eligible_at=clock_timestamp()+make_interval(secs=>:delay),updated_at=clock_timestamp() "
        "WHERE job_id=:id",
        id=job["job_id"],
        state=state,
        version=version,
        error=error,
        delay=delay,
    )
    execute(
        connection,
        "UPDATE v2_ingestion_attempts SET outcome=:outcome,error_code=:error,"
        "ended_at=clock_timestamp() WHERE job_id=:id AND attempt_number=:attempt AND "
        "outcome='running'",
        id=job["job_id"],
        attempt=job["attempt_count"],
        outcome=outcome,
        error=error,
    )
    project(connection, job, state, error)


def claim(engine: Engine, submission_id: str | None = None) -> dict[str, Any] | None:
    fingerprint = execution_identity()["execution_sha256"]
    with transaction(engine) as connection:
        values: dict[str, Any] = {"execution": fingerprint, "submission": None}
        extra = ""
        if submission_id is not None:
            values["submission"] = uid(submission_id)
            extra = " AND j.submission_id=:submission"
        eligible = (
            "(j.state='queued' OR (j.state='retry_wait' AND j.eligible_at<=clock_timestamp()) "
            "OR (j.state='running' AND j.lease_until<=clock_timestamp()))"
        )
        condition = (
            "FROM v2_ingestion_jobs j JOIN v2_ingestion_submissions s USING(submission_id) "
            "WHERE " + eligible + " AND s.execution_sha256=:execution "
            "AND s.contract='daily-ingestion-v2'" + extra
        )
        # Lock a canonical import before its job; official jobs have no import.
        candidate = one(
            connection,
            "SELECT i.import_id "
            "FROM v2_canonical_imports i JOIN v2_ingestion_jobs j USING(import_id) "
            "JOIN v2_ingestion_submissions s ON s.submission_id=j.submission_id WHERE "
            + eligible
            + " AND s.execution_sha256=:execution"
            + extra
            + " ORDER BY j.created_at,j.job_id LIMIT 1 FOR UPDATE OF i SKIP LOCKED",
            **values,
        )
        if candidate is not None:
            job = one(
                connection,
                "SELECT * FROM v2_ingestion_jobs WHERE import_id=:id FOR UPDATE SKIP LOCKED",
                id=candidate["import_id"],
            )
        else:
            job = one(
                connection,
                "SELECT j.* " + condition + " AND j.import_id IS NULL "
                "ORDER BY j.created_at,j.job_id LIMIT 1 FOR UPDATE OF j SKIP LOCKED",
                **values,
            )
        if job is None:
            return None
        # Import lock acquisition does not prevent an independent heartbeat.
        # Recheck eligibility after the job row is locked, using current DB time.
        eligible_now = execute(
            connection,
            "SELECT (j.state='queued' OR (j.state='retry_wait' AND "
            "j.eligible_at<=clock_timestamp())"
            "OR (j.state='running' AND j.lease_until<=clock_timestamp())) "
            "AND s.execution_sha256=:execution AND s.contract=:contract "
            "FROM v2_ingestion_jobs j JOIN v2_ingestion_submissions s USING(submission_id) "
            "WHERE j.job_id=:id",
            id=job["job_id"],
            execution=fingerprint,
            contract=PROTOCOL,
        ).scalar_one()
        if not eligible_now:
            return None
        if job["cancel_requested"]:
            finish(connection, job, "cancelled", "cancelled")
            return None
        if job["state"] == "running":
            execute(
                connection,
                "UPDATE v2_ingestion_attempts SET outcome='expired',ended_at=clock_timestamp(),"
                "error_code='lease_expired' WHERE job_id=:id AND attempt_number=:attempt "
                "AND outcome='running'",
                id=job["job_id"],
                attempt=job["attempt_count"],
            )
        if job["attempt_count"] >= 3:
            finish(connection, job, "failed", "expired", "attempts_exhausted")
            return None
        owner = uuid4()
        execute(
            connection,
            "UPDATE v2_ingestion_jobs SET state='running',attempt_count=attempt_count+1,"
            "fencing_token=fencing_token+1,owner=:owner,lease_until=clock_timestamp()+interval "
            "'60 seconds',"
            "revision=revision+1,error_code=NULL,updated_at=clock_timestamp() WHERE job_id=:id",
            id=job["job_id"],
            owner=owner,
        )
        job = one(connection, "SELECT * FROM v2_ingestion_jobs WHERE job_id=:id", id=job["job_id"])
        assert job is not None
        execute(
            connection,
            "INSERT INTO v2_ingestion_attempts (job_id,attempt_number,fencing_token,owner,"
            "execution_sha256,started_at,outcome) VALUES (:id,:attempt,:token,:owner,:execution,"
            "clock_timestamp(),'running')",
            id=job["job_id"],
            attempt=job["attempt_count"],
            token=job["fencing_token"],
            owner=owner,
            execution=fingerprint,
        )
        project(connection, job, "running", None)
        return job


def fence(connection: Connection, current: dict[str, Any]) -> dict[str, Any]:
    job = lock_job(connection, current["job_id"])
    valid = execute(
        connection,
        "SELECT state='running' AND owner=:owner AND fencing_token=:token "
        "AND lease_until>clock_timestamp() FROM v2_ingestion_jobs WHERE job_id=:id",
        id=current["job_id"],
        owner=current["owner"],
        token=current["fencing_token"],
    ).scalar_one()
    if not valid:
        raise V2Error("ownership_lost", "Ingestion ownership expired")
    if job["cancel_requested"]:
        raise V2Error("cancelled", "Ingestion cancellation requested")
    return job


def heartbeat(engine: Engine, current: dict[str, Any]) -> bool:
    with transaction(engine) as connection:
        result = execute(
            connection,
            "UPDATE v2_ingestion_jobs SET lease_until=clock_timestamp()+interval '60 seconds' "
            "WHERE job_id=:id AND state='running' AND owner=:owner AND fencing_token=:token "
            "AND lease_until>clock_timestamp() AND NOT cancel_requested RETURNING job_id",
            id=current["job_id"],
            owner=current["owner"],
            token=current["fencing_token"],
        ).first()
        return result is not None


def fail(engine: Engine, current: dict[str, Any], error: Exception) -> None:
    with transaction(engine) as connection:
        job = lock_job(connection, current["job_id"])
        valid = execute(
            connection,
            "SELECT state='running' AND owner=:owner AND fencing_token=:token AND "
            "lease_until>clock_timestamp() FROM v2_ingestion_jobs WHERE job_id=:id",
            id=current["job_id"],
            owner=current["owner"],
            token=current["fencing_token"],
        ).scalar_one()
        if not valid:
            return
        if job["cancel_requested"]:
            finish(connection, job, "cancelled", "cancelled")
            return
        transient = bool(getattr(error, "transient", False))
        retry = transient and job["attempt_count"] < 3
        delay = max(
            10 if job["attempt_count"] == 1 else 30,
            min(3600, int(getattr(error, "retry_after", 0))),
        )
        code = error.code if isinstance(error, V2Error) else "operation_failed"
        finish(
            connection,
            job,
            "retry_wait" if retry else "failed",
            "transient" if retry else "permanent",
            code,
            delay=delay if retry else 0,
        )


def cancel(engine: Engine, job_id: str, revision: int, key: str) -> dict[str, Any]:
    identity = uid(job_id)
    if type(revision) is not int or revision < 0:
        raise V2Error("invalid_request", "Invalid job revision")
    request = {"job_id": job_id, "expected_revision": revision}
    with transaction(engine) as connection:
        old = operation(connection, "cancel", key, request)
        if old is not None:
            return old
        job = lock_job(connection, identity)
        if job["revision"] != revision:
            raise V2Error("revision_conflict", "Job revision is stale")
        if job["state"] in {"succeeded", "failed"}:
            raise V2Error("revision_conflict", "Terminal ingestion cannot be cancelled")
        if job["state"] == "cancelled" or job["cancel_requested"]:
            pass
        elif job["state"] == "running":
            execute(
                connection,
                "UPDATE v2_ingestion_jobs SET cancel_requested=true,revision=revision+1,"
                "updated_at=clock_timestamp() WHERE job_id=:id",
                id=identity,
            )
        else:
            finish(connection, job, "cancelled", "cancelled")
        result = one(connection, "SELECT * FROM v2_ingestion_jobs WHERE job_id=:id", id=identity)
        assert result is not None
        return save_operation(connection, "cancel", key, request, result)


def inspect_submission(engine: Engine, submission_id: str) -> dict[str, Any]:
    sid = uid(submission_id)
    with engine.connect() as connection:
        current = one(
            connection, "SELECT * FROM v2_ingestion_submissions WHERE submission_id=:id", id=sid
        )
        if current is None:
            raise V2Error("not_found", "Submission not found")
        rows = [
            dict(row)
            for row in execute(
                connection,
                "SELECT * FROM v2_ingestion_jobs WHERE submission_id=:id ORDER BY job_id LIMIT 62",
                id=sid,
            ).mappings()
        ]
        for row in rows:
            row["attempts"] = [
                dict(v)
                for v in execute(
                    connection,
                    "SELECT * FROM v2_ingestion_attempts WHERE job_id=:id ORDER BY "
                    "attempt_number LIMIT 3",
                    id=row["job_id"],
                ).mappings()
            ]
        return cast(
            dict[str, Any],
            wire(
                {
                    "submission": current,
                    "jobs": rows,
                    "execution_compatible": current["execution_sha256"]
                    == execution_identity()["execution_sha256"],
                }
            ),
        )
