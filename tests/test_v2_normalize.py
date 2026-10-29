"""Offline v2 exact-format, bounded allocation, provenance and readback acceptance."""

import hashlib
import zipfile
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from marketlab.datasets.v2 import source as source_module
from marketlab.datasets.v2.artifacts import verify_dataset, verify_parquet
from marketlab.datasets.v2.common import DEFAULT_LIMITS, V2Error, canonical_json, digest
from marketlab.datasets.v2.core import metadata_hash, registry_request
from marketlab.datasets.v2.normalize import COLUMNS, INPUT_TYPES, normalize_source
from marketlab.datasets.v2.source import download_official, official_metadata

DAY = date(2025, 3, 1)
ID = "binance:spot:SOLUSDT"
HEADER = ",".join(COLUMNS) + "\n"
ROW = "2,2025-03-01T00:00:00.123456Z,1.25,2.000000000000000001,2.5,,false"


def instrument() -> dict[str, Any]:
    return registry_request(
        dict(
            venue_id="binance",
            market="spot",
            source_symbol="SOLUSDT",
            base_asset="SOL",
            quote_asset="USDT",
            display_name="Solana / USDT",
            trade_id_order="numeric",
            adapter="binance_daily",
        )
    )


def metadata(path: Path, kind: str = "csv", encoding: str = "rfc3339_utc") -> dict[str, Any]:
    return dict(
        schema="canonical-trade-import-v1",
        instrument_id=ID,
        trade_date=DAY.isoformat(),
        format=kind,
        timestamp_encoding=encoding,
        quote_quantity_mode="supplied",
        source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        source_name="binance-test-export",
        source_reference=None,
        coverage_claim="observed_only",
    )


def csv_file(tmp_path: Path, rows: list[str] | None = None, header: str = HEADER) -> Path:
    path = tmp_path / "input.csv"
    path.write_text(
        header + "\n".join([ROW] if rows is None else rows) + "\n", encoding="utf-8", newline=""
    )
    return path


def normalize(path: Path, output: Path, **kwargs: Any) -> dict[str, Any]:
    return normalize_source(
        path,
        output,
        metadata=kwargs.pop("metadata", metadata(path)),
        instrument=instrument(),
        **kwargs,
    )


def test_csv_exact_decimals_nulls_dedup_numeric_order_and_full_readback(tmp_path: Path) -> None:
    path = csv_file(tmp_path, [ROW.replace("2,", "10,", 1), ROW, ROW])
    quality = normalize(path, tmp_path / "output")
    assert (quality["raw_rows"], quality["accepted_rows"], quality["duplicate_rows"]) == (3, 2, 1)
    rows = pq.ParquetFile(tmp_path / "output/trades.parquet").read().to_pylist()
    assert [row["source_trade_id"] for row in rows] == ["2", "10"]
    assert rows[0]["quantity"] == Decimal("2.000000000000000001")
    assert rows[0]["is_buyer_maker"] is None and rows[0]["is_best_match"] is False
    assert rows[0]["executed_at"] == datetime(2025, 3, 1, 0, 0, 0, 123456, tzinfo=UTC)
    verify_parquet(tmp_path / "output/trades.parquet", quality, instrument_id=ID, trade_date=DAY)


@pytest.mark.parametrize(
    ("encoding", "value"),
    [
        ("unix_seconds", "1740787200"),
        ("unix_milliseconds", "1740787200123"),
        ("unix_microseconds", "1740787200123456"),
        ("rfc3339_utc", "2025-03-01T00:00:00+00:00"),
        ("rfc3339_utc", "2025-03-01T23:59:59.999999Z"),
    ],
)
def test_explicit_timestamp_encodings(tmp_path: Path, encoding: str, value: str) -> None:
    path = csv_file(tmp_path, [ROW.replace("2025-03-01T00:00:00.123456Z", value)])
    q = normalize(path, tmp_path / "output", metadata=metadata(path, encoding=encoding))
    verify_parquet(tmp_path / "output/trades.parquet", q, instrument_id=ID, trade_date=DAY)


@pytest.mark.parametrize(
    "replacement",
    [
        "2025-03-01T00:00:00",
        "2025-03-01T00:00:00+01:00",
        "2025-03-01T00:00:00.1234567Z",
        "2025-02-28T23:59:59.999999Z",
        "2025-03-02T00:00:00Z",
        "2025-03-01T00:00:60Z",
    ],
)
def test_timestamp_rejections(tmp_path: Path, replacement: str) -> None:
    path = csv_file(tmp_path, [ROW.replace("2025-03-01T00:00:00.123456Z", replacement)])
    with pytest.raises(V2Error):
        normalize(path, tmp_path / "output")


@pytest.mark.parametrize(
    "bad",
    [
        "0",
        "-1",
        "+1",
        "1e2",
        "NaN",
        "Infinity",
        "1,000",
        "0.1234567890123456789",
        "100000000000000000000",
    ],
)
@pytest.mark.parametrize("field", [2, 3, 4])
def test_invalid_decimal_and_missing_quote_rejected(tmp_path: Path, bad: str, field: int) -> None:
    values = ROW.split(",")
    values[field] = bad
    path = csv_file(tmp_path, [",".join(values)])
    with pytest.raises(V2Error):
        normalize(path, tmp_path / "output")


@pytest.mark.parametrize("bad", ["01", "-1", "+1", "1.0", "opaque", "9223372036854775808", ""])
def test_invalid_numeric_ids(tmp_path: Path, bad: str) -> None:
    path = csv_file(tmp_path, [ROW.replace("2,", bad + ",", 1)])
    with pytest.raises(V2Error):
        normalize(path, tmp_path / "output")


def test_empty_missing_extra_duplicate_header_and_conflicting_ids(tmp_path: Path) -> None:
    for index, (header, rows) in enumerate(
        [
            (HEADER, []),
            (HEADER.replace("quote_quantity,", ""), [ROW]),
            (HEADER.rstrip() + ",extra\n", [ROW + ",x"]),
            (HEADER.replace("quote_quantity", "quantity"), [ROW]),
            (HEADER, [ROW, ROW.replace("1.25", "1.26")]),
        ]
    ):
        path = csv_file(tmp_path, rows, header)
        with pytest.raises(V2Error):
            normalize(path, tmp_path / f"output{index}")


def test_bom_reordered_columns_and_strict_flags(tmp_path: Path) -> None:
    path = tmp_path / "input.csv"
    values = ROW.split(",")
    path.write_text(
        "\ufeff" + ",".join(reversed(COLUMNS)) + "\n" + ",".join(reversed(values)) + "\n",
        encoding="utf-8",
    )
    assert normalize(path, tmp_path / "output")["accepted_rows"] == 1
    for index, bad in enumerate(["True", "0", "null", "FALSE", " "]):
        path = csv_file(tmp_path, [ROW.replace(",,false", f",{bad},false")])
        with pytest.raises(V2Error):
            normalize(path, tmp_path / f"bad{index}")


@pytest.mark.parametrize(
    "bound",
    [
        "source_bytes",
        "rows",
        "record_bytes",
        "metadata_bytes",
        "logical_bytes",
        "parquet_bytes",
        "scratch_bytes",
    ],
)
def test_lowered_resource_bounds_fail_closed(tmp_path: Path, bound: str) -> None:
    path = csv_file(tmp_path, [ROW, ROW.replace("2,", "3,", 1)])
    with pytest.raises(V2Error):
        normalize(path, tmp_path / "output", limits=replace(DEFAULT_LIMITS, **{bound: 1}))


def test_source_hash_mismatch_and_cancellation(tmp_path: Path) -> None:
    path = csv_file(tmp_path)
    meta = metadata(path)
    meta["source_sha256"] = "0" * 64
    with pytest.raises(V2Error):
        normalize(path, tmp_path / "output", metadata=meta)
    with pytest.raises(V2Error, match="cancelled"):
        normalize(path, tmp_path / "output", cancelled=lambda: True)


def test_canonical_parquet_exact_logical_equivalence(tmp_path: Path) -> None:
    path = csv_file(tmp_path)
    first = normalize(path, tmp_path / "first")
    canonical = tmp_path / "canonical.parquet"
    data = pq.ParquetFile(tmp_path / "first/trades.parquet").read().drop(["instrument_id"])
    pq.write_table(data, canonical)
    second = normalize(
        canonical,
        tmp_path / "second",
        metadata=metadata(canonical, "parquet", "arrow_timestamp_us_utc"),
    )
    assert first["logical_sha256"] == second["logical_sha256"]
    assert metadata_hash(metadata(path)) != metadata_hash(
        metadata(canonical, "parquet", "arrow_timestamp_us_utc")
    )


@pytest.mark.parametrize("bad_type", [pa.float64(), pa.decimal128(20, 2), pa.string()])
def test_parquet_implicit_price_casts_rejected(tmp_path: Path, bad_type: Any) -> None:
    path = tmp_path / "input.parquet"
    values = [
        "2",
        datetime(2025, 3, 1, tzinfo=UTC),
        1.25
        if pa.types.is_floating(bad_type)
        else Decimal("1.25")
        if pa.types.is_decimal(bad_type)
        else "1.25",
        Decimal("2"),
        Decimal("2.5"),
        None,
        False,
    ]
    types = list(INPUT_TYPES)
    types[2] = bad_type
    table = pa.Table.from_pylist(
        [dict(zip(COLUMNS, values, strict=True))],
        schema=pa.schema([pa.field(k, t) for k, t in zip(COLUMNS, types, strict=True)]),
    )
    pq.write_table(table, path)
    with pytest.raises(V2Error):
        normalize(
            path, tmp_path / "output", metadata=metadata(path, "parquet", "arrow_timestamp_us_utc")
        )


@pytest.mark.parametrize(
    ("day", "encoding", "instant"),
    [
        (date(2024, 12, 31), "unix_milliseconds", 1735603200123),
        (DAY, "unix_microseconds", 1740787200123456),
    ],
)
def test_official_archive_timestamp_units_and_checksum(
    tmp_path: Path, day: date, encoding: str, instant: int
) -> None:
    path = tmp_path / f"SOLUSDT-trades-{day.isoformat()}.zip"
    payload = f"10,1.25,2,2.5,{instant},True,False\n2,1.25,2,2.5,{instant},False,True\n"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(path.stem + ".csv", payload)
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    path.with_name(path.name + ".CHECKSUM").write_text(f"{sha}  {path.name}\n")
    meta = official_metadata(ID, day, sha)
    assert meta["timestamp_encoding"] == encoding
    q = normalize(path, tmp_path / "output", metadata=meta)
    assert q["expanded_bytes"] == len(payload)
    verify_parquet(tmp_path / "output/trades.parquet", q, instrument_id=ID, trade_date=day)
    path.with_name(path.name + ".CHECKSUM").write_text("0" * 64 + "  " + path.name + "\n")
    with pytest.raises(V2Error, match="checksum"):
        normalize(path, tmp_path / "bad", metadata=meta)


def test_official_zip_member_security(tmp_path: Path) -> None:
    for index, member in enumerate(["../bad.csv", "other.csv"]):
        path = tmp_path / "SOLUSDT-trades-2025-03-01.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(member, "ignored")
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        path.with_name(path.name + ".CHECKSUM").write_text(f"{sha}  {path.name}\n")
        with pytest.raises(V2Error):
            normalize(path, tmp_path / f"out{index}", metadata=official_metadata(ID, DAY, sha))


def test_full_dataset_verification_and_tampering(tmp_path: Path) -> None:
    source = csv_file(tmp_path)
    meta = metadata(source)
    inst = instrument()
    output = tmp_path / "output"
    q = normalize(source, output)
    identity = dict(
        source_sha256=meta["source_sha256"],
        metadata_sha256=metadata_hash(meta),
        instrument_semantic_sha256=inst["semantic_sha256"],
        trade_date=DAY.isoformat(),
        schema_version="spot-trades-v2",
        transform_version="binance-spot-trades-v2",
        lock_sha256="a" * 64,
    )
    version = digest(identity)
    manifest = dict(
        schema="dataset-manifest-v2",
        dataset_version_id=version,
        identity=identity,
        instrument=inst,
        metadata=meta,
        source=dict(
            kind="canonical_file",
            origin_verification="operator_declared",
            source_sha256=meta["source_sha256"],
        ),
        build=dict(execution_sha256="b" * 64, lock_sha256="a" * 64),
        quality=q,
        artifact=dict(path="trades.parquet", sha256=q["parquet_sha256"], bytes=q["parquet_bytes"]),
    )
    (output / "quality.json").write_bytes(canonical_json(q))
    (output / "manifest.json").write_bytes(canonical_json(manifest))
    expected = dict(
        dataset_version_id=version,
        manifest_sha256=hashlib.sha256((output / "manifest.json").read_bytes()).hexdigest(),
    )
    assert verify_dataset(output, expected)["dataset_version_id"] == version
    with pytest.raises(V2Error):
        verify_dataset(output, dict(manifest_sha256="0" * 64))
    original = (output / "quality.json").read_bytes()
    (output / "quality.json").write_bytes(b"{}\n")
    with pytest.raises(V2Error):
        verify_dataset(output)
    (output / "quality.json").write_bytes(original)
    with (output / "trades.parquet").open("ab") as stream:
        stream.write(b"corrupt")
    with pytest.raises(V2Error):
        verify_dataset(output)


def test_official_downloader_request_policy_and_provider_supplied_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = tmp_path / "fixture.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("SOLUSDT-trades-2025-03-01.csv", "2,1.25,2,2.49,1740787200000000,True,False\n")
    content = archive.read_bytes()
    sha = hashlib.sha256(content).hexdigest()
    seen = []
    original = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        body = (
            (sha + "  SOLUSDT-trades-2025-03-01.zip\n").encode()
            if request.url.path.endswith("CHECKSUM")
            else content
        )
        return httpx.Response(
            200, headers={"content-length": str(len(body))}, stream=httpx.ByteStream(body)
        )

    def client(**kwargs: Any) -> httpx.Client:
        assert kwargs == dict(trust_env=False, follow_redirects=False, timeout=30.0)
        return original(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(source_module.httpx, "Client", client)
    result = download_official(tmp_path / "download", instrument(), DAY)
    assert seen[0].endswith(".CHECKSUM") and len(seen) == 2
    q = normalize(result["source_path"], tmp_path / "output", metadata=result["metadata"])
    row = pq.ParquetFile(tmp_path / "output/trades.parquet").read().to_pylist()[0]
    assert row["quote_quantity"] == Decimal("2.49")
    assert q["accepted_rows"] == 1


@pytest.mark.parametrize(
    ("status", "transient"), [(404, False), (302, False), (408, True), (429, True), (503, True)]
)
def test_source_failure_no_retry_or_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: int, transient: bool
) -> None:
    original = httpx.Client
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            status, headers={"retry-after": "99999"}, stream=httpx.ByteStream(b"")
        )

    monkeypatch.setattr(
        source_module.httpx,
        "Client",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    with pytest.raises(V2Error) as found:
        download_official(tmp_path / "download", instrument(), DAY)
    assert len(calls) == 1
    assert bool(getattr(found.value, "transient", False)) is transient
    if transient:
        assert found.value.retry_after == 3600


def test_leading_zero_decimal_digits_are_normalized_not_rejected(tmp_path: Path) -> None:
    path = csv_file(tmp_path, [ROW.replace("1.25", "01.25").replace("2.5,", "00.01,")])
    q = normalize(path, tmp_path / "output")
    row = pq.ParquetFile(tmp_path / "output/trades.parquet").read().to_pylist()[0]
    assert row["price"] == Decimal("1.25") and row["quote_quantity"] == Decimal("0.01")
    verify_parquet(tmp_path / "output/trades.parquet", q, instrument_id=ID, trade_date=DAY)


def test_exact_lowered_bounds_pass_one_over_rejects(tmp_path: Path) -> None:
    path = csv_file(tmp_path)
    first = normalize(path, tmp_path / "reference")
    ceilings = dict(
        source_bytes=path.stat().st_size,
        rows=1,
        record_bytes=max(len(line) for line in path.read_bytes().splitlines(keepends=True)),
        metadata_bytes=len(canonical_json(metadata(path))),
        logical_bytes=first["logical_input_bytes"],
        parquet_bytes=first["parquet_bytes"],
        expanded_bytes=path.stat().st_size,
    )
    for index, (field, maximum) in enumerate(ceilings.items()):
        assert (
            normalize(
                path, tmp_path / f"exact{index}", limits=replace(DEFAULT_LIMITS, **{field: maximum})
            )["accepted_rows"]
            == 1
        )
        if maximum > 1:
            with pytest.raises(V2Error):
                normalize(
                    path,
                    tmp_path / f"over{index}",
                    limits=replace(DEFAULT_LIMITS, **{field: maximum - 1}),
                )


def test_parquet_allocation_admission_and_decoded_arrow_bytes(tmp_path: Path) -> None:
    from marketlab.datasets.v2.normalize import checked_parquet

    path = csv_file(tmp_path)
    normalize(path, tmp_path / "first")
    canonical = tmp_path / "canonical.parquet"
    table = pq.ParquetFile(tmp_path / "first/trades.parquet").read().drop(["instrument_id"])
    pq.write_table(table, canonical)
    q = normalize(
        canonical,
        tmp_path / "second",
        metadata=metadata(canonical, "parquet", "arrow_timestamp_us_utc"),
    )
    assert q["expanded_bytes"] == table.nbytes
    with pytest.raises(V2Error):
        checked_parquet(canonical, COLUMNS, INPUT_TYPES, replace(DEFAULT_LIMITS, scratch_bytes=1))
    with pytest.raises(V2Error):
        checked_parquet(canonical, COLUMNS, INPUT_TYPES, replace(DEFAULT_LIMITS, footer_bytes=1))
    corrupt = tmp_path / "bad.parquet"
    corrupt.write_bytes(b"PAR1" + b"\xff" * 4 + b"PAR1")
    with pytest.raises(V2Error):
        checked_parquet(corrupt, COLUMNS, INPUT_TYPES, DEFAULT_LIMITS)


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("build", "lock_sha256", "c" * 64),
        ("build", "execution_sha256", "bad"),
        ("source", "kind", "official_archive"),
        ("source", "origin_verification", "independently_verified"),
        ("source", "source_sha256", "0" * 64),
    ],
)
def test_manifest_source_and_build_provenance_is_checked(
    tmp_path: Path, section: str, field: str, value: str
) -> None:
    path = csv_file(tmp_path)
    meta = metadata(path)
    inst = instrument()
    output = tmp_path / "output"
    quality = normalize(path, output)
    identity = dict(
        source_sha256=meta["source_sha256"],
        metadata_sha256=metadata_hash(meta),
        instrument_semantic_sha256=inst["semantic_sha256"],
        trade_date=DAY.isoformat(),
        schema_version="spot-trades-v2",
        transform_version="binance-spot-trades-v2",
        lock_sha256="a" * 64,
    )
    manifest = dict(
        schema="dataset-manifest-v2",
        dataset_version_id=digest(identity),
        identity=identity,
        instrument=inst,
        metadata=meta,
        source=dict(
            kind="canonical_file",
            origin_verification="operator_declared",
            source_sha256=meta["source_sha256"],
        ),
        build=dict(execution_sha256="b" * 64, lock_sha256="a" * 64),
        quality=quality,
        artifact=dict(
            path="trades.parquet", sha256=quality["parquet_sha256"], bytes=quality["parquet_bytes"]
        ),
    )
    (output / "quality.json").write_bytes(canonical_json(quality))
    (output / "manifest.json").write_bytes(canonical_json(manifest))
    # Historical execution provenance remains readable without matching current source.
    verify_dataset(output)
    manifest[section][field] = value
    (output / "manifest.json").write_bytes(canonical_json(manifest))
    with pytest.raises(V2Error):
        verify_dataset(output)
