"""Real-clock acceptance on isolated tables in owned PostgreSQL 55435 only."""

import argparse
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from uuid import uuid4

import sqlalchemy as sa

from marketlab.config import Settings
from marketlab.datasets import jobs as r2
from marketlab.datasets.source import DatasetError, TransientSourceError
from marketlab.research import store as r4
from marketlab.research.spec import ResearchError, ResearchSpec

BASE = Path("artifacts/r4-clock")
TABLES = (
    "ingestion_submissions",
    "ingestion_jobs",
    "ingestion_attempts",
    "research_submissions",
    "research_runs",
    "research_attempts",
    "research_results",
)
SPEC = ResearchSpec.create(
    {
        "schema": "research-spec-v1",
        "workflow": "market_profile",
        "symbols": ["BTCUSDT"],
        "dataset_versions": ["a" * 64],
        "history_start": "2025-01-01T00:00:00Z",
        "start": "2025-01-01T01:00:00Z",
        "end": "2025-01-01T01:15:00Z",
        "interval": "5m",
        "metrics": ["profile"],
        "parameters": {},
        "predicates": {},
    }
).body()


def save(name, value):
    BASE.mkdir(exist_ok=True)
    (BASE / name).write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")


def now(engine):
    with engine.connect() as c:
        return c.scalar(sa.select(sa.func.clock_timestamp()))


class API:
    def __init__(self, kind, engine, prefix):
        self.kind, self.engine, self.prefix = kind, engine, prefix
        self.table = r2.jobs if kind == "R2" else r4.runs

    def new(self, key):
        key = self.prefix + "." + key
        if self.kind == "R2":
            return r2.submit(self.engine, ["BTCUSDT"], date(2025, 1, 1), date(2025, 1, 2), key)
        return r4.submit(self.engine, key, SPEC, {"clock_acceptance": True})[0]

    def claim(self, identity=None):
        return (
            r2.claim(self.engine, submission_id=identity)
            if self.kind == "R2"
            else r4.claim(self.engine, identity)
        )

    def identity(self, claim):
        return claim.submission_id if self.kind == "R2" else claim.run_id

    def row(self, identity):
        col = self.table.c.submission_id if self.kind == "R2" else self.table.c.run_id
        with self.engine.connect() as c:
            return dict(c.execute(sa.select(self.table).where(col == identity)).mappings().one())

    def heartbeat(self, claim):
        return (
            r2.heartbeat(self.engine, claim)
            if self.kind == "R2"
            else r4.heartbeat(self.engine, claim)
        )

    def fail(self, claim, transient=False):
        if self.kind == "R2":
            error = (
                TransientSourceError("clock acceptance retry")
                if transient
                else DatasetError("clock acceptance terminal")
            )
            r2.fail(self.engine, claim, error)
        else:
            r4.fail(self.engine, claim, transient)

    def stale(self, claim):
        expected = r2.OwnershipLost if self.kind == "R2" else ResearchError
        assert not self.heartbeat(claim)
        for operation in ("fence", "finish", "failure"):
            rejected = False
            try:
                if operation == "failure":
                    self.fail(claim)
                else:
                    with self.engine.connect() as c:
                        transaction = c.begin()
                        try:
                            if self.kind == "R2":
                                if operation == "fence":
                                    r2.fence(c, claim)
                                else:
                                    r2.succeed(c, claim, "a" * 64)
                            elif operation == "fence":
                                r4.fence(c, claim)
                            else:
                                r4.finish(c, claim)
                        finally:
                            transaction.rollback()
            except expected:
                rejected = True
            assert rejected, (self.kind, "stale mutation accepted", operation)


def stress(api, count=1000):
    started = time.monotonic()
    failures = []
    successes = 0
    for index in range(count):
        identity = api.new("stress." + str(index))
        claim = api.claim(identity)
        if claim is None:
            row = api.row(identity)
            failures.append(
                {
                    "index": index,
                    "eligible_at": row["eligible_at"],
                    "database_now": now(api.engine),
                    "state": row["state"],
                }
            )
        else:
            assert claim.attempt == 1 and claim.token == 1
            successes += 1
            api.fail(claim)
        if index % 100 == 0 or index == count - 1:
            print(
                json.dumps({"kind": api.kind, "requests": index + 1, "ineligible": len(failures)}),
                flush=True,
            )
    return {
        "new_requests": count,
        "immediate_claims": successes,
        "ineligible": failures,
        "claim_calls_per_request": 1,
        "seconds": time.monotonic() - started,
    }


def concurrency(api):
    with ThreadPoolExecutor(8) as pool:
        identities = list(pool.map(lambda _: api.new("replay"), range(16)))
    assert len(set(identities)) == 1
    claim = api.claim(identities[0])
    assert claim is not None
    api.fail(claim)
    conflict = False
    try:
        if api.kind == "R2":
            r2.submit(
                api.engine, ["ETHUSDT"], date(2025, 1, 1), date(2025, 1, 2), api.prefix + ".replay"
            )
        else:
            r4.submit(
                api.engine,
                api.prefix + ".replay",
                {**SPEC, "end": "2025-01-01T01:20:00Z"},
                {"clock_acceptance": True},
            )
    except (DatasetError, ResearchError):
        conflict = True
    assert conflict
    identities = [api.new("skip." + str(i)) for i in range(8)]
    first = api.row(identities[0])
    primary = "job_id" if api.kind == "R2" else "run_id"
    barrier = threading.Barrier(7)

    def one(_):
        barrier.wait(timeout=10)
        return api.claim()

    with api.engine.connect() as c:
        transaction = c.begin()
        c.execute(
            sa.select(api.table).where(api.table.c[primary] == first[primary]).with_for_update()
        ).one()
        try:
            with ThreadPoolExecutor(7) as pool:
                claims = list(pool.map(one, range(7)))
            assert all(claim is not None for claim in claims)
            found = {api.identity(claim) for claim in claims}
            assert len(found) == 7 and identities[0] not in found
        finally:
            transaction.rollback()
    final = api.claim(identities[0])
    assert final is not None
    for claim in [*claims, final]:
        api.fail(claim)
    return {
        "concurrent_replay_calls": 16,
        "unique_run_or_submission": 1,
        "conflict_rejected": True,
        "locked_row_skipped": True,
        "parallel_unique_claims": 7,
        "held_row_claimed_after_release": True,
    }


def wait_db(engine, deadlines, limit):
    started = time.monotonic()
    before = now(engine)
    while now(engine) < max(deadlines):
        assert time.monotonic() - started < limit, (
            "DB deadline did not advance within bounded wall time"
        )
        time.sleep(0.25)
    return {
        "database_before": before,
        "database_after": now(engine),
        "monotonic_wait_seconds": time.monotonic() - started,
    }


def retries(apis):
    evidence = {api.kind: [] for api in apis}
    ids = [api.new("retry") for api in apis]
    claims = [api.claim(identity) for api, identity in zip(apis, ids, strict=True)]
    assert all(c is not None for c in claims)
    for attempt, delay in ((1, 10), (2, 30)):
        deadlines = []
        for api, identity, claim in zip(apis, ids, claims, strict=True):
            api.fail(claim, True)
            row = api.row(identity)
            assert row["state"] == "retry_wait" and row["attempt_count"] == attempt
            assert api.claim(identity) is None
            assert abs((row["eligible_at"] - row["updated_at"]).total_seconds() - delay) < 0.1
            deadlines.append(row["eligible_at"])
        waited = wait_db(apis[0].engine, deadlines, delay + 15)
        assert waited["monotonic_wait_seconds"] >= delay - 1, (
            "retry became eligible too early in real time"
        )
        claims = [api.claim(identity) for api, identity in zip(apis, ids, strict=True)]
        for api, claim in zip(apis, claims, strict=True):
            assert claim is not None and claim.attempt == attempt + 1 and claim.token == attempt + 1
            evidence[api.kind].append({"delay": delay, "early_claim_rejected": True, **waited})
    for api, identity, claim in zip(apis, ids, claims, strict=True):
        api.fail(claim, True)
        assert api.claim(identity) is None
        row = api.row(identity)
        assert row["state"] == "failed" and row["attempt_count"] == 3
    return evidence


def leases(apis):
    ids = [api.new("expiry") for api in apis]
    claims = [api.claim(identity) for api, identity in zip(apis, ids, strict=True)]
    cycle_started = time.monotonic()
    live_ids = [api.new("heartbeat") for api in apis]
    live = [api.claim(identity) for api, identity in zip(apis, live_ids, strict=True)]
    assert all(c is not None for c in [*claims, *live])
    originals = [
        api.row(identity)["lease_until"] for api, identity in zip(apis, live_ids, strict=True)
    ]
    stop = threading.Event()
    samples = []
    failures = []
    started = time.monotonic()

    def heartbeat():
        while not stop.wait(10):
            for api, claim in zip(apis, live, strict=True):
                try:
                    assert api.heartbeat(claim)
                    samples.append(
                        {
                            "kind": api.kind,
                            "elapsed": time.monotonic() - started,
                            "database_now": now(api.engine),
                            "lease_until": api.row(api.identity(claim))["lease_until"],
                        }
                    )
                except BaseException as error:
                    failures.append(type(error).__name__)
                    stop.set()

    keeper = threading.Thread(target=heartbeat, daemon=True)
    keeper.start()
    phases = []
    try:
        for attempt in (1, 2, 3):
            deadlines = [
                api.row(identity)["lease_until"] for api, identity in zip(apis, ids, strict=True)
            ]
            waited = wait_db(apis[0].engine, deadlines, 75)
            elapsed = time.monotonic() - cycle_started
            assert elapsed >= 59, "60s lease expired too early in real time"
            waited["lease_elapsed_monotonic_seconds"] = elapsed
            for api, old in zip(apis, claims, strict=True):
                api.stale(old)
            following = [api.claim(identity) for api, identity in zip(apis, ids, strict=True)]
            cycle_started = time.monotonic()
            for api, old, new in zip(apis, claims, following, strict=True):
                if attempt < 3:
                    assert (
                        new is not None
                        and new.attempt == attempt + 1
                        and new.token == old.token + 1
                    )
                    assert new.owner != old.owner
                    api.stale(old)
                else:
                    assert new is None
                    row = api.row(api.identity(old))
                    assert (
                        row["state"] == "failed"
                        and row["attempt_count"] == 3
                        and row["fencing_token"] == 3
                    )
            phases.append({"expired_attempt": attempt, "deadlines": deadlines, **waited})
            claims = following
            print(
                json.dumps(
                    {"phase": "real60s-lease", "expired_attempt": attempt, **waited}, default=str
                ),
                flush=True,
            )
            if attempt == 1:
                wait_db(apis[0].engine, originals, 5)
                time.sleep(1)
                stop.set()
                keeper.join(timeout=5)
                assert not keeper.is_alive() and not failures and len(samples) >= 12
                for api, identity, claim in zip(apis, live_ids, live, strict=True):
                    assert api.row(identity)["lease_until"] > now(api.engine)
                    assert api.claim(identity) is None
                    api.fail(claim)
    finally:
        stop.set()
        keeper.join(timeout=5)
    return {
        "actual60s_expiry_rounds": phases,
        "heartbeat_interval_seconds": 10,
        "heartbeats": samples,
        "heartbeat_failures": failures,
        "fourth_attempt_rejected": True,
        "stale_heartbeat_fence_finish_failure_rejected": True,
        "lease_or_eligibility_edits": 0,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--after-fix", action="store_true", required=True)
    p.parse_args()
    settings = Settings()
    url = settings.sqlalchemy_url
    assert url.host == "127.0.0.1" and url.port == 55435
    assert url.database == "marketlab" and url.username == "marketlab"
    recorded = json.loads((BASE / "resource-ownership.json").read_text(encoding="utf-8-sig"))[0]
    assert recorded["Name"] == "/marketlab-clock-pg-20261024"
    assert recorded["Config"]["Labels"]["marketlab.clock.owner"] == "clock-20261024"
    engine = sa.create_engine(url, connect_args=settings.database_connect_args, pool_size=12)
    schema = "r4_clock_" + uuid4().hex
    isolated = engine.execution_options(schema_translate_map={None: schema})
    result = {
        "schema": schema,
        "clock_lease_eligibility_edits": 0,
        "scope": "durable functions; source/analytics/publication covered by retained suite",
    }
    created = False
    started = time.monotonic()
    try:
        with engine.begin() as c:
            assert (
                c.scalar(sa.text("SELECT version_num FROM public.alembic_version"))
                == "0005_research"
            )
            result["public_counts_before"] = {
                name: c.scalar(sa.text(f"SELECT count(*) FROM public.{name}"))
                for name in (*TABLES, "trades", "dataset_versions")
            }
            c.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
            created = True
            for name in TABLES:
                c.execute(
                    sa.text(f'CREATE TABLE "{schema}".{name} (LIKE public.{name} INCLUDING ALL)')
                )
        apis = [API(kind, isolated, schema + "." + kind) for kind in ("R2", "R4")]
        result["stress"] = {api.kind: stress(api, 1000) for api in apis}
        save("acceptance-progress.json", result)
        assert all(
            v["immediate_claims"] == 1000 and not v["ineligible"] for v in result["stress"].values()
        )
        result["concurrency"] = {api.kind: concurrency(api) for api in apis}
        result["retry_eligibility"] = retries(apis)
        save("acceptance-progress.json", result)
        result["leases"] = leases(apis)
        with engine.connect() as c:
            result["public_counts_after"] = {
                name: c.scalar(sa.text(f"SELECT count(*) FROM public.{name}"))
                for name in (*TABLES, "trades", "dataset_versions")
            }
        assert result["public_counts_before"] == result["public_counts_after"]
        result["seconds"] = time.monotonic() - started
        assert result["seconds"] < 600
        result["passed"] = True
    except BaseException as error:
        result["passed"] = False
        result["error_type"] = type(error).__name__
        result["error"] = (
            str(error) if isinstance(error, AssertionError) else "bounded acceptance failure"
        )
        save("acceptance-failed.json", result)
        raise
    finally:
        if created:
            assert schema.startswith("r4_clock_") and len(schema) == 41
            with engine.begin() as c:
                c.execute(sa.text(f'DROP SCHEMA "{schema}" CASCADE'))
            result["owned_schema_removed"] = True
        engine.dispose()
    save("acceptance-complete.json", result)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
