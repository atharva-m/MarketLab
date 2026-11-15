"""Read-only HTTP observations of lease recovery on a small PostgreSQL fixture."""

from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from test_v2_browser_imports_integration import browser_engine  # noqa: F401
from test_v2_copilot_integration import model_engine  # noqa: F401
from test_v2_ingestion_integration import body as ingestion_body
from test_v2_ingestion_integration import v2_engine  # noqa: F401
from test_v2_research import body as research_body
from test_v2_research_integration import fixture_version, research_engine  # noqa: F401
from test_v2_workers_integration import migrate

from marketlab.analytics.bars import BarService
from marketlab.copilot.v2 import durable
from marketlab.copilot.v2 import store as copilot_store
from marketlab.copilot.v2.model import CopilotModel
from marketlab.copilot.v2.routes import router as model_routes
from marketlab.copilot.v2.service import CopilotService
from marketlab.datasets.v2 import admission, jobs
from marketlab.datasets.v2.browser_imports import BrowserImports
from marketlab.datasets.v2.core import execute
from marketlab.datasets.v2.routes import router as dataset_routes
from marketlab.memos.v2.model import MemoModel
from marketlab.memos.v2.service import MemoService
from marketlab.research.v2 import store as research_store
from marketlab.research.v2.routes import router as research_routes
from marketlab.research.v2.service import ResearchService
from marketlab.research.v2.spec import ResearchSpec

pytestmark = pytest.mark.integration


def worker(engine, label, kind, *, heartbeat_age=0):
    host, root, instance = [str(uuid4()) for _ in range(3)]
    with engine.begin() as connection:
        execute(
            connection,
            "INSERT INTO v2_worker_hosts(host_id,operator_label) VALUES (:host,:label)",
            host=host,
            label=label,
        )
        execute(
            connection,
            "INSERT INTO v2_worker_roots(root_id,host_id,local_path,boot_identity) "
            "VALUES (:root,:host,'private-root-path','private-boot-id')",
            root=root,
            host=host,
        )
        execute(
            connection,
            "INSERT INTO v2_worker_instances (instance_id,root_id,source_sha256,lock_sha256,"
            "boot_identity,native_identity,state,heartbeat_at) VALUES "
            "(:instance,:root,:sha,:sha,'private-boot-id','private-native-id','ready',"
            "clock_timestamp()-make_interval(secs=>:age))",
            instance=instance,
            root=root,
            sha="a" * 64,
            age=heartbeat_age,
        )
        execute(
            connection,
            "INSERT INTO v2_worker_capabilities (instance_id,kind,contract,execution_sha256) "
            "VALUES (:instance,:kind,'test-contract',:sha)",
            instance=instance,
            kind=kind,
            sha="a" * 64,
        )
    return engine.execution_options(worker_instance_id=instance), instance, host


def app_for(engine, storage):
    storage.mkdir(exist_ok=True)
    base = BarService(engine, storage, None)
    research = ResearchService(base)
    copilot = CopilotService(research, CopilotModel("http://unused.invalid"))
    memo = MemoService(research, MemoModel("http://unused.invalid"))
    app = FastAPI()
    app.include_router(dataset_routes)
    app.include_router(research_routes)
    app.include_router(model_routes)
    app.state.v2_import_service = BrowserImports(engine, storage)
    app.state.v2_research_service = research
    app.state.v2_copilot_service = copilot
    app.state.v2_memo_service = memo
    return app, research, copilot, memo


async def get(client, path, **params):
    response = await client.get(path, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def expire(connection, table, identity, value):
    execute(
        connection,
        f"UPDATE {table} SET lease_until=clock_timestamp()-interval '1 second' "
        f"WHERE {identity}=:id",
        id=value,
    )


async def test_legacy_status_keeps_raw_attempts_and_unknown_attribution(v2_engine, tmp_path):  # noqa: F811
    app, research, _, _ = app_for(v2_engine, tmp_path / "storage")
    submitted = jobs.submit(v2_engine, ingestion_body(), "legacy-projection")
    submission_id = submitted["submission_id"]
    assert jobs.claim(v2_engine, submission_id) is not None
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            page = await get(client, "/v2/workers")
            assert page["registry_available"] is False and page["items"] == []
            response = await get(client, f"/v2/ingestion/submissions/{submission_id}")
            job = response["jobs"][0]
            assert "worker_instance_id" not in job["attempts"][0]
            status = job["execution_status"]
            assert status["current_attempt"] == 1 and status["successful_attempt"] is None
            attempt = status["attempts"][0]
            assert attempt["lease_valid"] is True
            assert (
                attempt["host_id"] is attempt["host_label"] is attempt["worker_instance_id"] is None
            )
    finally:
        await research.close()
        await research.base.close()


async def test_execution_status_recovery_and_inventory_on_four_routes(model_engine, tmp_path):  # noqa: F811
    engine = model_engine
    migrate(engine, "0012_v2_storage")
    migrate(engine, "0013_v2_workers")
    ec2, ec2_id, ec2_host = worker(engine, "EC2", "research", heartbeat_age=90)
    windows, windows_id, windows_host = worker(engine, "Windows", "research")
    storage = tmp_path / "storage"
    admission.initialize(engine, storage)
    version = fixture_version(engine, storage, tmp_path)
    app, research, copilot, memo = app_for(engine, storage)
    peer_base = BarService(windows, storage, None)
    peer = ResearchService(peer_base)
    try:
        spec = ResearchSpec.create(
            {
                **research_body(),
                "instrument_ids": ["binance:spot:BTCUSDT"],
                "dataset_versions": [version],
            }
        )
        run, _ = await research.submit(spec, "execution-projection")
        research_path = f"/v2/research/runs/{run}"
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            queued = (await get(client, research_path))["execution_status"]
            assert queued["attempts"] == [] and queued["current_attempt"] is None
            # A real database claim attributed to a fixture worker identity.
            first = research_store._claim(ec2, research.execution, run, None)
            assert first is not None
            initial = (await get(client, research_path))["execution_status"]
            assert initial["current_attempt"] == 1
            assert initial["attempts"][0]["host_id"] == ec2_host
            first_worker = (await get(client, "/v2/workers", instance_id=ec2_id))["items"][0]
            assert first_worker["fresh"] is False
            assert first_worker["active_work"] == [
                {"kind": "research", "identity": run, "parent_id": None, "attempt_number": 1}
            ]
            with engine.begin() as connection:
                execute(
                    connection,
                    "UPDATE v2_research_runs SET owner=:other WHERE run_id=:id",
                    other=uuid4(),
                    id=run,
                )
            unfenced = (await get(client, research_path))["execution_status"]
            assert (
                unfenced["current_attempt"] is None
                and unfenced["attempts"][0]["lease_valid"] is False
            )
            with engine.begin() as connection:
                execute(
                    connection,
                    "UPDATE v2_research_runs SET owner=:owner WHERE run_id=:id",
                    owner=first.owner,
                    id=run,
                )
                expire(connection, "v2_research_runs", "run_id", run)
            expired = (await get(client, research_path))["execution_status"]
            assert (
                expired["current_attempt"] is None
                and expired["attempts"][0]["lease_valid"] is False
            )
            assert (await get(client, "/v2/workers", instance_id=ec2_id))["items"][0][
                "active_work"
            ] == []
            assert await peer.work(1, run) == 1
            finished = await get(client, research_path)
            status = finished["execution_status"]
            assert status["current_attempt"] is None and status["successful_attempt"] == 2
            assert [a["outcome"] for a in status["attempts"]] == ["expired", "succeeded"]
            assert [
                (a["host_id"], a["host_label"], a["worker_instance_id"]) for a in status["attempts"]
            ] == [(ec2_host, "EC2", ec2_id), (windows_host, "Windows", windows_id)]
            assert [a["fencing_token"] for a in status["attempts"]] == [1, 2]
            assert all(
                a["ended_at"].endswith("Z") and a["lease_valid"] is None for a in status["attempts"]
            )
            results = await get(client, f"{research_path}/results")
            assert results["profiles"]["binance:spot:BTCUSDT"]["coverage"]["observed"] == 8

            # The published numerical run queues an independent memo; only claim it.
            assert durable.claim(windows, "memo", memo.execution, run) is not None
            memo_info = await get(client, f"{research_path}/memo")
            assert memo_info["execution"] == memo.execution and memo_info["calls"] == []
            assert memo_info["execution_status"]["attempts"][0]["worker_instance_id"] == windows_id

            request_id, _, _ = copilot_store.create(
                engine, {"schema": "copilot-request-v2"}, {}, copilot.execution, "status-copilot"
            )
            current = durable.claim(windows, "copilot", copilot.execution, request_id)
            assert current is not None
            request_status = await get(client, f"/v2/copilot/requests/{request_id}")
            revision = request_status["revisions"][0]
            assert str(revision["job_id"]) == current.identity
            assert revision["calls"] == [] and revision["execution_status"]["current_attempt"] == 1
            assert revision["execution_status"]["attempts"][0]["host_label"] == "Windows"

            submission = jobs.submit(engine, ingestion_body(), "status-ingestion")["submission_id"]
            ingestion_job = jobs.claim(windows, submission)
            assert ingestion_job is not None
            assert jobs.cancel(
                engine, str(ingestion_job["job_id"]), ingestion_job["revision"], "cancel-ingestion"
            )
            ingestion = (await get(client, f"/v2/ingestion/submissions/{submission}"))["jobs"][0]
            assert ingestion["cancel_requested"] is True
            assert ingestion["execution_status"]["attempts"][0]["host_id"] == windows_host

            first_page = await get(client, "/v2/workers", limit=1)
            second_page = await get(
                client, "/v2/workers", limit=1, cursor=first_page["next_cursor"]
            )
            survivors = first_page["items"] + second_page["items"]
            assert {row["instance_id"] for row in survivors} == {ec2_id, windows_id}
            assert second_page["next_cursor"] is None
            visible = next(row for row in survivors if row["instance_id"] == windows_id)
            assert visible["capabilities"] == ["research"]
            assert {row["kind"]: row["parent_id"] for row in visible["active_work"]} == {
                "copilot": request_id,
                "ingestion": submission,
                "memo": None,
            }
            assert set(visible) == {
                "instance_id",
                "host_id",
                "host_label",
                "state",
                "heartbeat_at",
                "registered_at",
                "fresh",
                "capabilities",
                "active_work",
                "active_work_truncated",
            }
            assert "private-" not in str(survivors)
            assert (await get(client, "/v2/workers", instance_id=str(uuid4())))["items"] == []
            for query in [
                "limit=0",
                "limit=1&limit=2",
                "unknown=1",
                "instance_id=invalid",
                f"cursor={ec2_id}&instance_id={ec2_id}",
            ]:
                response = await client.get(f"/v2/workers?{query}")
                assert response.status_code == 422
    finally:
        await peer.close()
        await peer_base.close()
        await research.close()
        await research.base.close()
