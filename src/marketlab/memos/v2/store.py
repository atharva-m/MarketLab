"""One immutable supplemental job per verified numerical result."""

from typing import Any

from sqlalchemy.engine import Connection, Engine

from marketlab.copilot.v2 import durable
from marketlab.datasets.v2.common import V2Error, canonical_json, digest
from marketlab.datasets.v2.core import execute, lock, one, transaction, uid, wire
from marketlab.research.v2.store import key_value


def register(
    connection: Connection,
    run_id: str,
    numerical: dict[str, Any],
    fingerprint: dict[str, Any],
    execution: dict[str, Any],
) -> bool:
    row = one(connection, "SELECT * FROM v2_memo_jobs WHERE run_id=:id", id=run_id)
    hashes = (numerical["manifest_sha256"], numerical["summary_sha256"], digest(fingerprint))
    if row is not None:
        if (
            tuple(
                row[k]
                for k in (
                    "numerical_manifest_sha256",
                    "summary_sha256",
                    "numerical_fingerprint_sha256",
                )
            )
            != hashes
        ):
            raise V2Error("integrity_failure", "Memo numerical identity mismatch")
        return True
    execute(
        connection,
        "INSERT INTO v2_memo_jobs "
        "(run_id,numerical_manifest_sha256,summary_sha256,numerical_fingerprint_sha256,"
        "execution_json,execution_sha256,lock_sha256) VALUES "
        "(:id,:manifest,:summary,:fingerprint,:execution,:execution_sha,:lock)",
        id=run_id,
        manifest=hashes[0],
        summary=hashes[1],
        fingerprint=hashes[2],
        execution=canonical_json(execution).decode(),
        execution_sha=digest(execution),
        lock=execution["lock_sha256"],
    )
    return False


def enqueue(
    engine: Engine,
    run_id: str,
    key: str,
    numerical: dict[str, Any],
    fingerprint: dict[str, Any],
    execution: dict[str, Any],
) -> bool:
    uid(run_id)
    key_value(key)
    body_hash = digest({"run_id": run_id, "schema": "memo-request-v2"})
    with transaction(engine) as connection:
        lock(connection, "v2-memo-enqueue:" + key)
        row = one(
            connection, "SELECT * FROM v2_research_runs WHERE run_id=:id FOR UPDATE", id=run_id
        )
        current = one(connection, "SELECT * FROM v2_research_results WHERE run_id=:id", id=run_id)
        if row is None or current is None or row["state"] != "succeeded" or current != numerical:
            raise V2Error("revision_conflict", "Memo requires a verified numerical success")
        old = one(
            connection, "SELECT * FROM v2_memo_operations WHERE idempotency_key=:key", key=key
        )
        if old is not None:
            if str(old["run_id"]) != run_id or old["request_sha256"] != body_hash:
                raise V2Error("revision_conflict", "Memo operation key conflict")
            return True
        replayed = register(connection, run_id, numerical, fingerprint, execution)
        execute(
            connection,
            "INSERT INTO v2_memo_operations (idempotency_key,run_id,request_sha256) VALUES "
            "(:key,:id,:hash)",
            key=key,
            id=run_id,
            hash=body_hash,
        )
        return replayed


def inspect(engine: Engine, run_id: str) -> dict[str, Any]:
    uid(run_id)
    with engine.connect() as connection:
        row = one(connection, "SELECT * FROM v2_memo_jobs WHERE run_id=:id", id=run_id)
        if row is None:
            raise V2Error("not_found", "Supplemental memo not found")
        result = durable.decoded(row, ("execution", "draft", "provenance"))
        if digest(result["execution"]) != result["execution_sha256"]:
            raise V2Error("integrity_failure", "Memo execution identity mismatch")
        result["calls"] = [
            dict(c)
            for c in execute(
                connection,
                "SELECT "
                "call_number,attempt_number,state,model_digest,input_sha256,response_sha256,"
                "reserved_at,finished_at FROM v2_memo_calls WHERE run_id=:id ORDER BY "
                "call_number",
                id=run_id,
            ).mappings()
        ]
    return wire({"schema": "memo-status-v2", **result})  # type: ignore[no-any-return]
