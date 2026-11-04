"""Shared bounded v2 inference ownership and nonrefundable call receipts."""

import json
import threading
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from sqlalchemy.engine import Connection, Engine

from marketlab.datasets.v2.common import V2Error, canonical_json, digest
from marketlab.datasets.v2.core import execute, one, transaction, uid


@dataclass(frozen=True)
class Claim:
    kind: str
    identity: str
    owner: str
    token: int
    attempt: int
    request_id: str | None = None
    revision: int | None = None
    relative_path: str | None = None
    lost: threading.Event = field(default_factory=threading.Event, compare=False)


def table(kind: str) -> tuple[str, str]:
    if kind not in {"copilot", "memo"}:
        raise ValueError("Unknown inference kind")
    return "v2_" + kind, "job_id" if kind == "copilot" else "run_id"


DUE = (
    "(j.state='queued' OR (j.state='retry_wait' AND j.eligible_at<=clock_timestamp()) "
    "OR (j.state='running' AND j.lease_until<=clock_timestamp()))"
)


def pending(engine: Engine, current_execution: dict[str, Any] | None = None) -> bool:
    from marketlab.copilot.store import pending as legacy_pending

    if legacy_pending(engine):
        return True
    with engine.connect() as connection:
        if execute(connection, "SELECT to_regclass('v2_copilot_jobs')").scalar_one() is None:
            return False
        if current_execution is None:
            from .model import execution

            current_execution = execution("copilot")
        return (
            execute(
                connection,
                "SELECT 1 FROM v2_copilot_jobs j JOIN v2_copilot_requests r USING(request_id) "
                "WHERE r.execution_sha256=:execution AND " + DUE + " LIMIT 1",
                execution=digest(current_execution),
            ).first()
            is not None
        )


def claim(
    engine: Engine, kind: str, execution: dict[str, Any], target: str | None = None
) -> Claim | None:
    prefix, ident = table(kind)
    if target is not None:
        uid(target)
    with transaction(engine) as connection:
        join = "JOIN v2_copilot_requests r USING(request_id)" if kind == "copilot" else ""
        compatibility = "r.execution_sha256" if kind == "copilot" else "j.execution_sha256"
        selector = "j.request_id" if kind == "copilot" else "j.run_id"
        for _ in range(64):
            row = one(
                connection,
                f"SELECT j.* FROM {prefix}_jobs j {join} WHERE {DUE} "
                f"AND {compatibility}=:execution AND (CAST(:target AS uuid) IS NULL OR "
                f"{selector}=:target) "
                f"ORDER BY j.created_at,j.{ident} LIMIT 1",
                execution=digest(execution),
                target=target,
            )
            if row is None:
                return None
            identity = str(row[ident])
            if kind == "copilot":
                request = one(
                    connection,
                    "SELECT * FROM v2_copilot_requests WHERE request_id=:id FOR UPDATE",
                    id=row["request_id"],
                )
                if (
                    request is None
                    or request["current_revision"] != row["revision"]
                    or request["run_id"] is not None
                ):
                    raise V2Error("integrity_failure", "Invalid pending interpretation revision")
            else:
                one(
                    connection,
                    "SELECT run_id FROM v2_research_runs WHERE run_id=:id FOR UPDATE",
                    id=identity,
                )
            row = one(
                connection,
                f"SELECT j.* FROM {prefix}_jobs j WHERE j.{ident}=:id AND {DUE} FOR UPDATE "
                f"SKIP LOCKED",
                id=identity,
            )
            if row is None:
                return None
            if row["state"] == "running":
                execute(
                    connection,
                    f"UPDATE {prefix}_attempts SET "
                    f"outcome='expired',ended_at=clock_timestamp() WHERE {ident}=:id AND "
                    f"attempt_number=:attempt AND outcome='running'",
                    id=identity,
                    attempt=row["attempt_count"],
                )
            if row["attempt_count"] >= 3:
                execute(
                    connection,
                    f"UPDATE {prefix}_jobs SET "
                    f"state='failed',owner=NULL,lease_until=NULL,"
                    f"error_code='attempts_exhausted',updated_at=clock_timestamp() WHERE "
                    f"{ident}=:id",
                    id=identity,
                )
                if kind == "copilot":
                    execute(
                        connection,
                        "UPDATE v2_copilot_revisions SET outcome='failed' WHERE request_id=:id "
                        "AND revision=:revision",
                        id=row["request_id"],
                        revision=row["revision"],
                    )
                continue
            attempt = row["attempt_count"] + 1
            token = row["fencing_token"] + 1
            owner, attempt_uuid = str(uuid4()), str(uuid4())
            relative = f"memos-v2/{identity}/{attempt_uuid}" if kind == "memo" else None
            execute(
                connection,
                f"UPDATE {prefix}_jobs SET "
                f"state='running',attempt_count=:attempt,fencing_token=:token,owner=:owner,"
                f"lease_until=clock_timestamp()+interval '60 "
                f"seconds',error_code=NULL,updated_at=clock_timestamp() WHERE {ident}=:id",
                attempt=attempt,
                token=token,
                owner=owner,
                id=identity,
            )
            extra_columns = ",attempt_uuid,relative_path" if kind == "memo" else ""
            extra_values = ",:attempt_uuid,:path" if kind == "memo" else ""
            execute(
                connection,
                f"INSERT INTO {prefix}_attempts "
                f"({ident},attempt_number,owner,fencing_token{extra_columns}) VALUES "
                f"(:id,:attempt,:owner,:token{extra_values})",
                id=identity,
                attempt=attempt,
                owner=owner,
                token=token,
                attempt_uuid=attempt_uuid,
                path=relative,
            )
            return Claim(
                kind,
                identity,
                owner,
                token,
                attempt,
                str(row["request_id"]) if kind == "copilot" else None,
                row.get("revision"),
                relative,
            )
    return None


def fence(connection: Connection, current: Claim) -> dict[str, Any]:
    prefix, ident = table(current.kind)
    if current.lost.is_set():
        raise V2Error("revision_conflict", "Inference ownership lost")
    if current.kind == "copilot":
        request = one(
            connection,
            "SELECT * FROM v2_copilot_requests WHERE request_id=:id FOR UPDATE",
            id=current.request_id,
        )
        if (
            request is None
            or request["current_revision"] != current.revision
            or request["run_id"] is not None
        ):
            raise V2Error("revision_conflict", "Interpretation revision changed")
    else:
        one(
            connection,
            "SELECT run_id FROM v2_research_runs WHERE run_id=:id FOR UPDATE",
            id=current.identity,
        )
    row = one(
        connection,
        f"SELECT * FROM {prefix}_jobs WHERE {ident}=:id AND state='running' AND owner=:owner "
        f"AND fencing_token=:token AND lease_until>clock_timestamp() FOR UPDATE",
        id=current.identity,
        owner=current.owner,
        token=current.token,
    )
    if row is None:
        raise V2Error("revision_conflict", "Inference ownership lost")
    return row


def heartbeat(engine: Engine, current: Claim) -> bool:
    prefix, ident = table(current.kind)
    if current.lost.is_set():
        return False
    with transaction(engine) as connection:
        return (
            execute(
                connection,
                f"UPDATE {prefix}_jobs SET lease_until=clock_timestamp()+interval '60 "
                f"seconds',updated_at=clock_timestamp() WHERE {ident}=:id AND state='running' "
                f"AND owner=:owner AND fencing_token=:token AND lease_until>clock_timestamp() "
                f"RETURNING {ident}",
                id=current.identity,
                owner=current.owner,
                token=current.token,
            ).first()
            is not None
        )


def reserve(engine: Engine, current: Claim, identities: dict[str, Any], model_digest: str) -> int:
    prefix, ident = table(current.kind)
    with transaction(engine) as connection:
        row = fence(connection, current)
        if row["model_calls"] >= 2:
            raise V2Error("invalid_request", "Model call budget exhausted")
        number = row["model_calls"] + 1
        execute(
            connection,
            f"UPDATE {prefix}_jobs SET model_calls=:number WHERE {ident}=:id",
            number=number,
            id=current.identity,
        )
        execute(
            connection,
            f"INSERT INTO {prefix}_calls "
            f"({ident},call_number,attempt_number,fencing_token,model_digest,input_sha256,"
            f"schema_sha256,prompt_sha256) VALUES "
            f"(:id,:number,:attempt,:token,:model,:input,:schema,:prompt)",
            id=current.identity,
            number=number,
            attempt=current.attempt,
            token=current.token,
            model=model_digest,
            input=identities["input_sha256"],
            schema=identities["schema_sha256"],
            prompt=identities["prompt_sha256"],
        )
        return int(number)


def checkpoint(
    engine: Engine,
    current: Claim,
    number: int,
    value: dict[str, Any] | None,
    provenance: dict[str, Any],
) -> None:
    from .model import copilot_versions

    prefix, ident = table(current.kind)
    raw = provenance.get("response")
    if (
        type(raw) is not str
        or len(raw.encode()) > 32768
        or len(canonical_json(provenance)) > 131072
        or (
            current.kind == "copilot"
            and any(provenance.get(key) != version for key, version in copilot_versions().items())
        )
    ):
        raise V2Error("integrity_failure", "Invalid bounded model receipt")
    import hashlib

    if hashlib.sha256(raw.encode()).hexdigest() != provenance.get("response_sha256"):
        raise V2Error("integrity_failure", "Model response receipt mismatch")
    with transaction(engine) as connection:
        fence(connection, current)
        row = one(
            connection,
            f"SELECT * FROM {prefix}_calls WHERE {ident}=:id AND call_number=:number FOR UPDATE",
            id=current.identity,
            number=number,
        )
        if (
            row is None
            or row["state"] != "reserved"
            or row["fencing_token"] != current.token
            or any(
                row[k] != provenance[k]
                for k in ("model_digest", "input_sha256", "schema_sha256", "prompt_sha256")
            )
        ):
            raise V2Error("integrity_failure", "Model checkpoint reservation mismatch")
        execute(
            connection,
            f"UPDATE {prefix}_calls SET "
            f"state=:state,response_text=:raw,response_sha256=:sha,provenance_json=:provenance,"
            f"finished_at=clock_timestamp() WHERE {ident}=:id AND call_number=:number",
            state="checkpointed" if value is not None else "failed",
            raw=raw,
            sha=provenance["response_sha256"],
            provenance=canonical_json(provenance).decode(),
            id=current.identity,
            number=number,
        )
        if value is not None:
            if current.kind == "copilot":
                execute(
                    connection,
                    "UPDATE v2_copilot_revisions SET "
                    "interpretation_json=:value,provenance_json=:provenance WHERE "
                    "request_id=:id AND revision=:revision",
                    value=canonical_json(value).decode(),
                    provenance=canonical_json(provenance).decode(),
                    id=current.request_id,
                    revision=current.revision,
                )
            else:
                execute(
                    connection,
                    "UPDATE v2_memo_jobs SET draft_json=:value,provenance_json=:provenance "
                    "WHERE run_id=:id",
                    value=canonical_json(value).decode(),
                    provenance=canonical_json(provenance).decode(),
                    id=current.identity,
                )


def complete(
    connection: Connection, current: Claim, state: str = "succeeded", error: str | None = None
) -> None:
    prefix, ident = table(current.kind)
    fence(connection, current)
    execute(
        connection,
        f"UPDATE {prefix}_attempts SET "
        f"outcome=:state,error_code=:error,ended_at=clock_timestamp() WHERE {ident}=:id AND "
        f"attempt_number=:attempt",
        state=state,
        error=error,
        id=current.identity,
        attempt=current.attempt,
    )
    execute(
        connection,
        f"UPDATE {prefix}_jobs SET "
        f"state=:state,owner=NULL,lease_until=NULL,error_code=:error,"
        f"eligible_at=clock_timestamp()+make_interval(secs=>:delay),"
        f"updated_at=clock_timestamp() WHERE {ident}=:id",
        state=state,
        error=error,
        delay=10 if current.attempt == 1 else 30,
        id=current.identity,
    )
    if current.kind == "copilot" and state == "failed":
        execute(
            connection,
            "UPDATE v2_copilot_revisions SET outcome='failed' WHERE request_id=:id AND "
            "revision=:revision",
            id=current.request_id,
            revision=current.revision,
        )


def fail(engine: Engine, current: Claim, transient: bool = False) -> None:
    with transaction(engine) as connection:
        row = fence(connection, current)
        retry = transient and current.attempt < 3 and row["model_calls"] < 2
        complete(
            connection,
            current,
            "retry_wait" if retry else "failed",
            "unavailable" if transient else "execution_failed",
        )


def decoded(row: dict[str, Any], names: tuple[str, ...]) -> dict[str, Any]:
    result = dict(row)
    for name in names:
        raw = result.pop(name + "_json")
        result[name] = json.loads(raw) if raw is not None else None
    return result
