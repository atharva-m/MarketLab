"""Focused checks for the checksum-bound small official ingestion worker."""

import hashlib
import zipfile
from contextlib import nullcontext
from dataclasses import replace
from datetime import date
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest

from marketlab import workers
from marketlab.config import Settings
from marketlab.datasets.v2 import admission, jobs, normalize, service, source
from marketlab.datasets.v2.common import DEFAULT_LIMITS, V2Error
from marketlab.datasets.v2.ingestion_budget import COMPACT_LIMITS, OfficialBudget
from marketlab.storage import store

SUBMISSION = "70fb0e01-1d9a-427a-b03a-855a479ff14c"
SOURCE_SHA = "1" * 64
DAY = date(2025, 3, 1)
INSTRUMENT = {"instrument_id": "binance:spot:BTCUSDT", "source_symbol": "BTCUSDT"}
OFFICIAL_JOB = {
    "submission_id": SUBMISSION,
    "source_mode": "official",
    "import_id": None,
    "child_count": 1,
    "actual_count": 1,
}


def test_compact_claim_and_storage_transfer_use_the_same_physical_bound(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    budget = OfficialBudget(SUBMISSION, SOURCE_SHA)
    job = OFFICIAL_JOB
    engine = Mock()
    engine.connect.return_value = nullcontext(Mock())
    monkeypatch.setattr(
        Settings, "__init__", lambda self: object.__setattr__(self, "storage_backend", "s3")
    )
    monkeypatch.setattr(store, "current", lambda _: True)
    monkeypatch.setattr(admission, "root_for", lambda _: tmp_path)
    monkeypatch.setattr(jobs, "one", lambda *a, **k: job)
    ticket = {"ticket_id": "exact"}
    acquire = Mock(return_value=ticket)
    claim = Mock(return_value=job.copy())
    monkeypatch.setattr(admission, "acquire", acquire)
    monkeypatch.setattr(jobs, "_claim", claim)
    current = jobs.claim(engine, SUBMISSION, budget=budget)
    assert current is not None
    acquire.assert_called_once_with(
        engine, tmp_path, "ingestion", budget.logical_bytes, physical_bytes=budget.physical_bytes
    )
    claim.assert_called_once_with(engine, SUBMISSION, ticket, budget=budget)
    reserve = Mock()
    monkeypatch.setattr(service, "_reserve", reserve)
    monkeypatch.setattr(service, "transaction", lambda _: nullcontext(None))
    monkeypatch.setattr(jobs, "fence", Mock())
    monkeypatch.setattr(admission, "mark_auxiliary_path", Mock())
    service._job_reservations(engine, tmp_path, current, "relative")
    assert sum(call.args[3] for call in reserve.call_args_list) == budget.physical_bytes
    assert reserve.call_args_list[0].kwargs["admission_ticket"] is ticket
    assert budget.physical_bytes == 1_476_530_176
    assert budget.logical_bytes == 402_788_352


@pytest.mark.parametrize("changed", [{"source_mode": "canonical"}, {"actual_count": 2}])
def test_compact_wrong_job_fails_before_reserving(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, changed: dict[str, object]
) -> None:
    engine = Mock()
    engine.connect.return_value = nullcontext(Mock())
    monkeypatch.setattr(
        Settings, "__init__", lambda self: object.__setattr__(self, "storage_backend", "s3")
    )
    monkeypatch.setattr(store, "current", lambda _: True)
    monkeypatch.setattr(admission, "root_for", lambda _: tmp_path)
    monkeypatch.setattr(jobs, "one", lambda *a, **k: {**OFFICIAL_JOB, **changed})
    acquire = Mock()
    monkeypatch.setattr(admission, "acquire", acquire)
    with pytest.raises(V2Error, match="one exact official job"):
        jobs.claim(engine, SUBMISSION, budget=OfficialBudget(SUBMISSION, SOURCE_SHA))
    acquire.assert_not_called()


def test_locked_ineligible_job_releases_unused_ticket_before_activation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    engine = Mock()
    connection = Mock()
    engine.connect.return_value = nullcontext(connection)
    monkeypatch.setattr(
        Settings, "__init__", lambda self: object.__setattr__(self, "storage_backend", "s3")
    )
    monkeypatch.setattr(store, "current", lambda _: True)
    monkeypatch.setattr(admission, "root_for", lambda _: tmp_path)
    ticket = {"ticket_id": "exact"}
    monkeypatch.setattr(admission, "acquire", Mock(return_value=ticket))
    finish, activate = Mock(), Mock()
    monkeypatch.setattr(admission, "finish", finish)
    monkeypatch.setattr(admission, "activate", activate)
    monkeypatch.setattr(workers, "guard", Mock())
    monkeypatch.setattr(jobs, "transaction", lambda _: nullcontext(connection))
    monkeypatch.setattr(jobs, "execution_identity", lambda: {"execution_sha256": SOURCE_SHA})
    monkeypatch.setattr(jobs, "one", lambda *_, **__: {**OFFICIAL_JOB, "job_id": SUBMISSION})
    sizes = Mock()
    sizes.mappings.return_value.one.return_value = {"child_count": 1, "actual_count": 1}
    ineligible = Mock()
    ineligible.scalar_one.return_value = False
    execute = Mock(side_effect=[sizes, ineligible])
    monkeypatch.setattr(jobs, "execute", execute)
    assert jobs.claim(engine, SUBMISSION, budget=OfficialBudget(SUBMISSION, SOURCE_SHA)) is None
    activate.assert_not_called()
    finish.assert_called_once_with(engine, ticket, 0)
    assert execute.call_count == 2


@pytest.mark.parametrize(
    "target", ["exact", "retained", "other", "wrong_fence", "orphan", "dead", "overflow"]
)
def test_root_audit_uses_transferred_bytes_only_for_the_exact_attempt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, target: str
) -> None:
    from marketlab.datasets.v2 import native_children

    budget = OfficialBudget(SUBMISSION, SOURCE_SHA)
    attempt = f"attempts-v2/{SUBMISSION}/2/6075d187-85c9-414b-be6f-84dd42556e6f"
    engine = Mock()
    connection = Mock()
    engine.connect.return_value.execution_options.return_value = nullcontext(connection)
    ticket = {
        "role": "ingestion",
        "ticket_id": SUBMISSION,
        "resource_id": SUBMISSION,
        "fencing_token": 2,
        "relative_path": None,
        "physical_bytes": 0,
        "ceiling_bytes": budget.logical_bytes,
        "native_identity": "{}",
    }
    transferred = {
        "ticket_id": SUBMISSION,
        "resource_id": SUBMISSION,
        "fencing_token": 2,
        "relative_path": attempt + "/output",
        "output": budget.output_bytes,
        "output_retained": 0,
        "scratch": budget.scratch_bytes,
        "scratch_retained": 0,
    }
    if target == "retained":
        transferred.update(
            output=0,
            output_retained=budget.output_bytes,
            scratch=0,
            scratch_retained=budget.scratch_bytes,
        )

    def rows(_, sql, **binds):
        if "FROM v2_worker_files" in sql or "FROM v2_research_reservations" in sql:
            return Mock(mappings=lambda: [])
        if "FROM v2_admission_tickets" in sql and "JOIN v2_storage_reservations" not in sql:
            return Mock(mappings=lambda: [ticket])
        assert "o.fencing_token=t.fencing_token" in sql
        assert "s.worker_root_id=o.worker_root_id" in sql
        assert binds == {
            "root": SUBMISSION,
            "output": budget.output_bytes,
            "scratch": budget.scratch_bytes,
            "logical": budget.logical_bytes,
        }
        return Mock(mappings=lambda: [] if target == "orphan" else [transferred])

    path = attempt + "/output/normalize.sqlite"
    if target == "other":
        path = path.replace("6075d187", "6075d188")
    if target == "wrong_fence":
        path = path.replace("/2/", "/3/")
    size = budget.physical_bytes + 1 if target == "overflow" else budget.logical_bytes + 1
    monkeypatch.setattr(admission, "_files", lambda *a, **k: [(path, size, 0, None)])
    monkeypatch.setattr(admission, "binding", lambda *a: {"epoch": 1})
    monkeypatch.setattr(workers, "local_root", lambda _: {"root_id": SUBMISSION})
    monkeypatch.setattr(workers, "execute", rows)
    monkeypatch.setattr(native_children, "alive", lambda _: target != "dead")
    if target in {"exact", "retained"}:
        workers._audit_root(engine, tmp_path, [])
    else:
        with pytest.raises(V2Error, match="Unmanaged|exceeds reservation"):
            workers._audit_root(engine, tmp_path, [])


def test_compact_pin_rejects_mismatching_checksum_before_archive(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    requests = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        checksum = f"{'2' * 64}  BTCUSDT-trades-{DAY}.zip\n".encode()
        return httpx.Response(200, stream=httpx.ByteStream(checksum))

    client = httpx.Client(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(source.httpx, "Client", lambda **_: client)
    with pytest.raises(V2Error, match="checksum differs"):
        source.download_official(
            tmp_path, INSTRUMENT, DAY, expected_sha256=SOURCE_SHA, limits=COMPACT_LIMITS
        )
    assert len(requests) == 1 and requests[0].endswith(".CHECKSUM")
    assert not (tmp_path / f"BTCUSDT-trades-{DAY}.zip").exists()


def _official_zip(tmp_path: Path, rows: str) -> tuple[Path, dict[str, object]]:
    archive = tmp_path / f"BTCUSDT-trades-{DAY}.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr(f"BTCUSDT-trades-{DAY}.csv", rows)
    source_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(".zip.CHECKSUM").write_text(
        f"{source_hash}  {archive.name}\n", encoding="ascii"
    )
    return archive, source.official_metadata(INSTRUMENT["instrument_id"], DAY, source_hash)


def test_compact_normalization_has_same_output_and_enforces_sqlite_bound(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    archive, metadata = _official_zip(
        tmp_path, "2,1,1,1,1740787200000002,True,False\n1,1,1,1,1740787200000001,False,True\n"
    )
    default = normalize.normalize_source(
        archive,
        tmp_path / "standard",
        metadata=metadata,
        instrument=INSTRUMENT,
        limits=DEFAULT_LIMITS,
    )
    sqlite_connect = normalize.sqlite3.connect
    statements = []

    def connect(path: Path) -> normalize.sqlite3.Connection:
        connection = sqlite_connect(path)
        connection.set_trace_callback(statements.append)
        return connection

    monkeypatch.setattr(normalize.sqlite3, "connect", connect)
    compact = normalize.normalize_source(
        archive,
        tmp_path / "compact",
        metadata=metadata,
        instrument=INSTRUMENT,
        limits=COMPACT_LIMITS,
    )
    assert default == compact
    assert "PRAGMA journal_mode=OFF" in statements
    assert "PRAGMA temp_store=MEMORY" in statements
    assert "PRAGMA page_size" in statements
    assert "PRAGMA max_page_count=262144" in statements
    assert not (tmp_path / "compact" / "normalize.sqlite").exists()


def test_compact_sqlite_page_exhaustion_does_not_exceed_reserved_disk(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    archive, metadata = _official_zip(
        tmp_path, "".join(f"{i},1,1,1,1740787200000001,True,False\n" for i in range(400))
    )
    limits = replace(COMPACT_LIMITS, scratch_bytes=8192)
    monkeypatch.setattr(normalize, "COMPACT_LIMITS", limits)
    output = tmp_path / "at-cap"
    original = Path.unlink
    sqlite_bytes = []

    def record_size(path: Path, missing_ok: bool = False) -> None:
        if path == output / "normalize.sqlite":
            sqlite_bytes.append(path.stat().st_size)
        original(path, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", record_size)
    with pytest.raises(V2Error, match="SQLite capacity exhausted") as raised:
        normalize.normalize_source(
            archive, output, metadata=metadata, instrument=INSTRUMENT, limits=limits
        )
    assert raised.value.code == "capacity_exceeded"
    assert len(sqlite_bytes) == 1 and sqlite_bytes[0] <= limits.scratch_bytes
    assert not list(output.iterdir())
