"""Bounded, read-only execution and worker projections for the workspace."""

from typing import Any, cast

from sqlalchemy.engine import Connection, Engine

from marketlab.datasets.v2.common import V2Error
from marketlab.datasets.v2.core import execute, uid, wire
from marketlab.workers import enabled

# These identifiers are fixed SQL fragments. Resource IDs and cursors are bound values.
_RESOURCES = {
    "ingestion": ("v2_ingestion_jobs", "job_id", "j.submission_id"),
    "research": ("v2_research_runs", "run_id", "NULL::uuid"),
    "copilot": ("v2_copilot_jobs", "job_id", "j.request_id"),
    "memo": ("v2_memo_jobs", "run_id", "NULL::uuid"),
}
_ATTEMPT_FIELDS = (
    "attempt_number",
    "fencing_token",
    "started_at",
    "ended_at",
    "outcome",
    "error_code",
    "host_id",
    "host_label",
    "worker_instance_id",
    "lease_valid",
)
_LIVE_LEASE = (
    "a.outcome='running' AND j.state='running' AND j.attempt_count=a.attempt_number "
    "AND j.owner=a.owner AND j.fencing_token=a.fencing_token "
    "AND j.lease_until>transaction_timestamp()"
)
_ACTIVE_WORK_LIMIT = 20


def attach_execution_status(
    connection: Connection,
    kind: str,
    resources: list[dict[str, Any]],
    *,
    include_raw_attempts: bool = False,
    registry_available: bool | None = None,
) -> None:
    """Read attempts in the same repeatable-read snapshot as their job statuses."""
    if not resources:
        return
    jobs, identity, _ = _RESOURCES[kind]
    if registry_available is None:
        registry_available = enabled(connection)
    observed_at = execute(connection, "SELECT transaction_timestamp()").scalar_one()
    host_fields = (
        "h.host_id,h.operator_label AS host_label"
        if registry_available
        else "NULL::uuid AS host_id,NULL::text AS host_label"
    )
    join = (
        "LEFT JOIN v2_worker_instances i ON i.instance_id=a.worker_instance_id "
        "LEFT JOIN v2_worker_roots r ON r.root_id=i.root_id "
        "LEFT JOIN v2_worker_hosts h ON h.host_id=r.host_id "
        if registry_available
        else ""
    )
    rows = execute(
        connection,
        f"SELECT a.*,{host_fields},CASE WHEN a.outcome='running' "
        f"THEN COALESCE(({_LIVE_LEASE}),false) END AS lease_valid,"
        "(j.state='succeeded' AND j.fencing_token=a.fencing_token "
        "AND a.outcome='succeeded') AS result_attempt "
        f"FROM v2_{kind}_attempts a JOIN {jobs} j USING ({identity}) "
        f"{join}WHERE a.{identity}=ANY(CAST(:identities AS uuid[])) "
        f"ORDER BY a.{identity},a.attempt_number",
        identities=[str(row[identity]) for row in resources],
    ).mappings()
    by_id = {row[identity]: row for row in resources}
    for row in resources:
        row["execution_status"] = {
            "observed_at": observed_at,
            "current_attempt": None,
            "successful_attempt": None,
            "attempts": [],
        }
        if include_raw_attempts:
            row["attempts"] = []
    for row in rows:
        resource = by_id[row[identity]]
        status = resource["execution_status"]
        status["attempts"].append({field: row.get(field) for field in _ATTEMPT_FIELDS})
        if row["lease_valid"]:
            status["current_attempt"] = row["attempt_number"]
        if row["result_attempt"]:
            status["successful_attempt"] = row["attempt_number"]
        if include_raw_attempts:
            # Keep the existing API shape. Only the new projection gains registry fields.
            resource["attempts"].append(
                {
                    field: value
                    for field, value in row.items()
                    if field not in {"host_id", "host_label", "lease_valid", "result_attempt"}
                }
            )


def worker_inventory(
    engine: Engine, limit: int = 25, cursor: str | None = None, instance_id: str | None = None
) -> dict[str, Any]:
    if (
        type(limit) is not int
        or not 1 <= limit <= 100
        or (cursor is not None and instance_id is not None)
    ):
        raise V2Error("invalid_request", "Invalid worker page")
    after = uid(cursor) if cursor is not None else None
    exact = uid(instance_id) if instance_id is not None else None
    with engine.connect() as connection:
        connection.execution_options(isolation_level="REPEATABLE READ")
        observed_at = execute(connection, "SELECT transaction_timestamp()").scalar_one()
        registry_available = enabled(connection)
        if not registry_available:
            return cast(
                dict[str, Any],
                wire(
                    {
                        "items": [],
                        "next_cursor": None,
                        "observed_at": observed_at,
                        "registry_available": False,
                    }
                ),
            )
        rows = [
            dict(row)
            for row in execute(
                connection,
                "SELECT i.instance_id,h.host_id,h.operator_label AS host_label,"
                "i.state,i.heartbeat_at,i.registered_at,"
                "i.heartbeat_at>transaction_timestamp()-interval '30 seconds' AS fresh "
                "FROM v2_worker_instances i JOIN v2_worker_roots r USING(root_id) "
                "JOIN v2_worker_hosts h USING(host_id) "
                "WHERE (CAST(:after AS uuid) IS NULL OR i.instance_id>:after) "
                "AND (CAST(:exact AS uuid) IS NULL OR i.instance_id=:exact) "
                "ORDER BY i.instance_id LIMIT :limit",
                after=after,
                exact=exact,
                limit=limit + 1,
            ).mappings()
        ]
        items = rows[:limit]
        if items:
            _attach_worker_details(connection, items)
    return cast(
        dict[str, Any],
        wire(
            {
                "items": items,
                "next_cursor": items[-1]["instance_id"] if len(rows) > limit else None,
                "observed_at": observed_at,
                "registry_available": True,
            }
        ),
    )


def _attach_worker_details(connection: Connection, items: list[dict[str, Any]]) -> None:
    workers = {row["instance_id"]: row for row in items}
    for row in items:
        row.update(capabilities=[], active_work=[], active_work_truncated=False)
    instances = list(workers)
    for row in execute(
        connection,
        "SELECT DISTINCT instance_id,kind FROM v2_worker_capabilities "
        "WHERE instance_id=ANY(CAST(:instances AS uuid[])) ORDER BY instance_id,kind",
        instances=instances,
    ).mappings():
        workers[row["instance_id"]]["capabilities"].append(row["kind"])
    for kind, (jobs, identity, parent) in _RESOURCES.items():
        # Cap each worker's results in SQL before combining the four kinds.
        for row in execute(
            connection,
            "SELECT w.instance_id,work.* FROM unnest(CAST(:instances AS uuid[])) w(instance_id) "
            f"JOIN LATERAL (SELECT a.{identity} AS identity,{parent} AS parent_id,"
            f"a.attempt_number FROM v2_{kind}_attempts a JOIN {jobs} j USING ({identity}) "
            f"WHERE a.worker_instance_id=w.instance_id AND {_LIVE_LEASE} "
            f"ORDER BY a.{identity} LIMIT :limit) work ON true "
            "ORDER BY w.instance_id,work.identity",
            instances=instances,
            limit=_ACTIVE_WORK_LIMIT + 1,
        ).mappings():
            worker = workers[row["instance_id"]]
            if len(worker["active_work"]) == _ACTIVE_WORK_LIMIT:
                worker["active_work_truncated"] = True
            else:
                worker["active_work"].append(
                    {
                        "kind": kind,
                        "identity": row["identity"],
                        "parent_id": row["parent_id"],
                        "attempt_number": row["attempt_number"],
                    }
                )
