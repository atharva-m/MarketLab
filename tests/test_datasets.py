"""Offline historical-source validation, bounds and exact normalization checks."""

import hashlib
import subprocess
import sys
import zipfile
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock

import httpx
import pyarrow.parquet as pq
import pytest
from sqlalchemy.engine import Engine

from marketlab.datasets import (
    DatasetError,
    Limits,
    download_archive,
    ingest_archive,
    normalize_archive,
)

DAY = date(2025, 1, 1)
MEMBER = "BTCUSDT-trades-2025-01-01.csv"
START = 1735689600000000
ROW = f"1,93500.123456789012345678,0.000000010000000001,0.000935001234567891,{START},True,False"


def archive_files(
    directory: Path,
    rows: list[str] | None = None,
    *,
    member: str = MEMBER,
    extra: bool = False,
    payload: bytes | None = None,
    symlink: bool = False,
) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    archive = directory / MEMBER.replace(".csv", ".zip")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
        info = zipfile.ZipInfo(member)
        if symlink:
            info.create_system = 3
            info.external_attr = 0o120777 << 16
        data = payload if payload is not None else ("\n".join(rows or [ROW]) + "\n").encode()
        output.writestr(info, data)
        if extra:
            output.writestr("other.csv", "ignored")
    checksum = archive.with_suffix(".zip.CHECKSUM")
    checksum.write_text(f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}\n")
    return archive, checksum


def normalize(archive: Path, output: Path, **kwargs: object) -> dict[str, object]:
    return normalize_archive(archive, output, symbol="BTCUSDT", trade_date=DAY, **kwargs)


def parquet_rows(output: Path) -> list[dict[str, object]]:
    files = list(output.rglob("*.parquet"))
    assert len(files) == 1
    return pq.ParquetFile(files[0]).read().to_pylist()


def test_normalization_preserves_historical_precision_time_and_numeric_id_order(
    tmp_path: Path,
) -> None:
    rows = [ROW.replace("1,", "10,", 1), ROW.replace("1,", "2,", 1), ROW]
    archive, _ = archive_files(tmp_path / "input", rows)
    normalize(archive, tmp_path / "output")
    result = parquet_rows(tmp_path / "output")
    assert [row["source_trade_id"] for row in result] == [1, 2, 10]
    assert result[0]["price"] == Decimal("93500.123456789012345678")
    assert result[0]["quantity"] == Decimal("0.000000010000000001")
    assert result[0]["quote_quantity"] == Decimal("0.000935001234567891")
    assert result[0]["executed_at"].isoformat() == "2025-01-01T00:00:00+00:00"
    assert result[0]["venue"] == "binance_spot"
    assert result[0]["symbol"] == "BTCUSDT"
    assert result[0]["is_buyer_maker"] is True
    assert result[0]["is_best_match"] is False


def test_exact_duplicates_collapse_and_logical_normalization_is_repeatable(tmp_path: Path) -> None:
    archive, _ = archive_files(tmp_path / "input", [ROW, ROW])
    first = normalize(archive, tmp_path / "first")
    second = normalize(archive, tmp_path / "second")
    assert len(parquet_rows(tmp_path / "first")) == 1
    assert first == second
    assert parquet_rows(tmp_path / "first") == parquet_rows(tmp_path / "second")


def test_conflicting_duplicate_blocks_publication(tmp_path: Path) -> None:
    archive, _ = archive_files(tmp_path / "input", [ROW, ROW.replace("True,False", "False,False")])
    with pytest.raises(DatasetError):
        normalize(archive, tmp_path / "output")


@pytest.mark.parametrize(
    ("column", "value"),
    [
        (0, "-1"),
        (0, "01"),
        (0, "9223372036854775808"),
        (0, "A"),
        (1, "0"),
        (1, "-1"),
        (1, "1e2"),
        (1, "NaN"),
        (1, "1.0000000000000000001"),
        (1, "100000000000000000000"),
        (2, "0"),
        (3, "Infinity"),
        (4, str(START - 1)),
        (4, str(START + 86_400_000_000)),
        (4, str(START // 1000)),
        (4, "1735689600000000.0"),
        (5, "true"),
        (5, "1"),
        (6, "false"),
        (6, ""),
    ],
)
def test_invalid_source_values_are_rejected(tmp_path: Path, column: int, value: str) -> None:
    fields = ROW.split(",")
    fields[column] = value
    archive, _ = archive_files(tmp_path / "input", [",".join(fields)])
    with pytest.raises(DatasetError):
        normalize(archive, tmp_path / "output")


@pytest.mark.parametrize("payload", [b"", b"\xff\xfe\n", b"a,b,c\n", (ROW + ",extra\n").encode()])
def test_malformed_or_empty_source_is_rejected(tmp_path: Path, payload: bytes) -> None:
    archive, _ = archive_files(tmp_path / "input", payload=payload)
    with pytest.raises(DatasetError):
        normalize(archive, tmp_path / "output")


@pytest.mark.parametrize("member", ["../" + MEMBER, "/" + MEMBER, "sub/" + MEMBER, "C:\\" + MEMBER])
def test_zip_paths_are_never_extracted(tmp_path: Path, member: str) -> None:
    archive, _ = archive_files(tmp_path / "input", member=member)
    with pytest.raises(DatasetError):
        normalize(archive, tmp_path / "output")
    assert not (tmp_path / MEMBER).exists()


@pytest.mark.parametrize("options", [{"extra": True}, {"symlink": True}])
def test_extra_or_symlink_archive_members_rejected(
    tmp_path: Path, options: dict[str, bool]
) -> None:
    archive, _ = archive_files(tmp_path / "input", **options)
    with pytest.raises(DatasetError):
        normalize(archive, tmp_path / "output")


def test_truncated_archive_rejected(tmp_path: Path) -> None:
    archive, _ = archive_files(tmp_path / "input")
    archive.write_bytes(archive.read_bytes()[:30])
    with pytest.raises(DatasetError):
        normalize(archive, tmp_path / "output")


@pytest.mark.parametrize(
    "limits",
    [Limits(compressed_bytes=1), Limits(expanded_bytes=1), Limits(rows=1), Limits(line_bytes=10)],
)
def test_source_limits_are_enforced(tmp_path: Path, limits: Limits) -> None:
    archive, _ = archive_files(tmp_path / "input", [ROW, ROW.replace("1,", "2,", 1)])
    with pytest.raises(DatasetError):
        normalize(archive, tmp_path / "output", limits=limits)


def test_checksum_mismatch_fails_before_database_access(tmp_path: Path) -> None:
    archive, checksum = archive_files(tmp_path / "input")
    checksum.write_text("0" * 64 + "  " + archive.name)
    engine = Mock(spec=Engine)
    with pytest.raises(DatasetError):
        ingest_archive(engine, tmp_path / "storage", archive, checksum)
    assert engine.mock_calls == []
    assert not list((tmp_path / "storage").rglob("manifest.json"))


@pytest.mark.parametrize("text", ["", "not-a-hash", "0" * 64 + "  wrong.zip", "0" * 5000])
def test_bad_checksum_documents_rejected_without_database(tmp_path: Path, text: str) -> None:
    archive, checksum = archive_files(tmp_path / "input")
    checksum.write_text(text)
    engine = Mock(spec=Engine)
    with pytest.raises(DatasetError):
        ingest_archive(engine, tmp_path / "storage", archive, checksum)
    assert engine.mock_calls == []


@pytest.mark.parametrize("failure", ["http", "redirect", "timeout", "disconnect", "truncated"])
def test_download_failures_are_bounded(tmp_path: Path, failure: str) -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("secret", request=request)
        if failure == "disconnect":
            raise httpx.ConnectError("secret", request=request)
        if failure == "redirect":
            return httpx.Response(302, headers={"location": "https://secret.invalid/"})
        if failure == "truncated":
            return httpx.Response(200, content=b"bad", headers={"Content-Length": "999"})
        return httpx.Response(503, content=b"secret")

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(DatasetError):
            download_archive(client, tmp_path / "download", symbol="BTCUSDT", trade_date=DAY)
    assert len(requests) <= 2
    assert all(request.url.host == "data.binance.vision" for request in requests)


def test_download_uses_expected_url_and_finite_request_timeouts(tmp_path: Path) -> None:
    archive, checksum = archive_files(tmp_path / "fixture")
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = (
            checksum.read_bytes()
            if request.url.path.endswith(".CHECKSUM")
            else archive.read_bytes()
        )
        return httpx.Response(200, content=body)

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        downloaded, downloaded_checksum, provenance = download_archive(
            client, tmp_path / "download", symbol="BTCUSDT", trade_date=DAY
        )
    assert downloaded.read_bytes() == archive.read_bytes()
    assert downloaded_checksum.read_bytes() == checksum.read_bytes()
    assert len(requests) == 2
    assert {request.url.path.rsplit("/", 1)[-1] for request in requests} == {
        archive.name,
        checksum.name,
    }
    assert all(request.url.host == "data.binance.vision" for request in requests)
    for request in requests:
        assert all(0 < timeout <= 30 for timeout in request.extensions["timeout"].values())
    assert provenance


def test_ingestion_help_module_is_available_without_services() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "marketlab.dataset_cli", "--help"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "ingest" in result.stdout and "inspect" in result.stdout


@pytest.mark.parametrize(
    "argv",
    [
        ["ingest", "--symbol", "ETHUSDT", "--date", "2025-01-01"],
        ["ingest", "--symbol", "BTCUSDT", "--date", "2025-01-02"],
        ["ingest", "--symbol", "BTCUSDT", "--date", "invalid"],
        ["inspect", "--version", "../../secret"],
    ],
)
def test_cli_rejects_out_of_scope_inputs_before_services(argv: list[str]) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "marketlab.dataset_cli", *argv],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("bounded_part", ["checksum", "archive"])
def test_download_streamed_byte_caps(tmp_path: Path, bounded_part: str) -> None:
    archive, checksum = archive_files(tmp_path / "fixture")
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith(".CHECKSUM"):
            body = b"x" * 4097 if bounded_part == "checksum" else checksum.read_bytes()
        else:
            body = archive.read_bytes()
        return httpx.Response(200, content=body)

    limits = Limits(compressed_bytes=1) if bounded_part == "archive" else Limits()
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(DatasetError, match="size limit"):
            download_archive(
                client, tmp_path / "download", symbol="BTCUSDT", trade_date=DAY, limits=limits
            )
    assert len(requests) == (1 if bounded_part == "checksum" else 2)


@pytest.mark.parametrize("failure", ["public", "private", "not_found", "output"])
def test_cli_safe_failures_have_no_stdout_and_dispose_engine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure: str,
) -> None:
    from types import SimpleNamespace

    from marketlab import dataset_cli

    engine = Mock(spec=Engine)
    monkeypatch.setattr(dataset_cli, "create_engine", lambda *args, **kwargs: engine)
    monkeypatch.setattr(
        dataset_cli,
        "Settings",
        lambda: SimpleNamespace(
            sqlalchemy_url="unused",
            database_connect_args={},
            storage_path=tmp_path,
        ),
    )

    def ingest(*args: object, **kwargs: object) -> dict[str, object]:
        if failure == "public":
            raise DatasetError("source checksum mismatch")
        if failure == "private":
            raise RuntimeError("SECRET password=secret SQL SELECT")
        return {"dataset_version_id": "a" * 64}

    monkeypatch.setattr(dataset_cli, "ingest_day", ingest)
    monkeypatch.setattr(dataset_cli, "inspect_version", lambda *args: None)
    argv = ["ingest", "--symbol", "BTCUSDT", "--date", "2025-01-01"]
    if failure == "not_found":
        argv = ["inspect", "--version", "a" * 64]
    if failure == "output":

        class BrokenOutput:
            def write(self, text: str) -> int:
                raise OSError("SECRET output path")

            def flush(self) -> None:
                return None

        with monkeypatch.context() as context:
            context.setattr(dataset_cli.sys, "stdout", BrokenOutput())
            result = dataset_cli.main(argv)
    else:
        result = dataset_cli.main(argv)
    assert result == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err.startswith("dataset-cli: ")
    assert "SECRET" not in output.err
    assert "password" not in output.err
    assert "SELECT" not in output.err
    assert "Traceback" not in output.err
    engine.dispose.assert_called_once()
