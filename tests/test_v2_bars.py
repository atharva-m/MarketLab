"""Generalized exact bars, selected identity proof and bounded lifecycle checks."""

import asyncio
import copy
import threading
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from sqlalchemy import create_engine

from marketlab.analytics.bars import BarError
from marketlab.analytics.bars import BarService as LegacyBarService
from marketlab.analytics.v2 import BarService, BarsRequest
from marketlab.analytics.v2.bars import (
    check_overlaps,
    numeric_bounds,
    overlapping_groups,
    valid_body,
)
from marketlab.datasets.normalize import SCHEMA as LEGACY_SCHEMA
from marketlab.datasets.normalize import VerificationCancelled
from marketlab.datasets.v2.core import registry_request
from marketlab.datasets.v2.normalize import SCHEMA

START = datetime(2025, 3, 1, tzinfo=UTC)
VERSION = "a" * 64
IDENTITY = "binance:spot:SOLUSDT"


def metadata(symbol="SOLUSDT", base="SOL", quote="USDT"):
    return registry_request(
        dict(
            venue_id="binance",
            market="spot",
            source_symbol=symbol,
            base_asset=base,
            quote_asset=quote,
            display_name=base + "/" + quote,
            trade_id_order="numeric",
            adapter="binance_daily",
        )
    )


def request(**changes):
    fields = dict(
        versions=[VERSION],
        instrument_id=IDENTITY,
        interval="1m",
        start=START,
        end=START + timedelta(minutes=5),
    )
    fields.update(changes)
    return BarsRequest.create(**fields)


def service(root, **changes):
    return BarService(LegacyBarService(create_engine("sqlite://"), root, **changes))


def partition(root, values, *, name="trades", legacy=False, identity=IDENTITY):
    path = root / (name + ".parquet")
    records = []
    for identifier, offset, price, quantity, quote in values:
        row = dict(
            source_trade_id=identifier if legacy else str(identifier),
            executed_at=START + timedelta(microseconds=offset),
            price=Decimal(price),
            quantity=Decimal(quantity),
            quote_quantity=Decimal(quote),
            is_buyer_maker=False,
            is_best_match=True,
        )
        row.update(venue="binance_spot", symbol="BTCUSDT") if legacy else row.update(
            instrument_id=identity
        )
        records.append(row)
    pq.write_table(
        pa.Table.from_pylist(records, schema=LEGACY_SCHEMA if legacy else SCHEMA),
        path,
        row_group_size=2,
    )
    return path


def selected(path, *, version=VERSION, identity=IDENTITY, meta=None):
    return dict(
        path=path,
        dataset_version_id=version,
        instrument_id=identity,
        trade_date=START.date(),
        metadata=meta or metadata(),
        semantic_sha256=(meta or metadata())["semantic_sha256"],
        manifest_sha256="b" * 64,
        id_bounds=numeric_bounds(path, threading.Event()),
        signature=(1,),
        catalog_identity=(version,),
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"instrument_id": "other:spot:SOLUSDT"},
        {"instrument_id": "binance:future:SOLUSDT"},
        {"instrument_id": "binance:spot:../SOL"},
        {"versions": [VERSION, VERSION]},
        {"versions": [True]},
        {"versions": []},
        {"versions": ["f" * 64] * 6},
        {"interval": "2m"},
        {"start": "2025-03-01"},
        {"start": "2025-03-01T00:00:00-01:00"},
        {"start": START.replace(tzinfo=None)},
        {"start": START + timedelta(microseconds=1)},
        {"end": START},
        {"end": START + timedelta(days=1, minutes=1)},
        {
            "interval": "5m",
            "start": START + timedelta(minutes=5),
            "end": START + timedelta(days=5, minutes=5),
        },
    ],
)
def test_request_rejects_invalid_or_excessive_selection(changes):
    with pytest.raises(BarError):
        request(**changes)


def test_request_exact_chart_limits_and_calendar_generalization():
    assert request(end=START + timedelta(days=1)).end == START + timedelta(days=1)
    assert request(interval="5m", end=START + timedelta(days=5)).seconds == 300
    assert request(start="1970-01-01T00:00:00Z", end="1970-01-01T00:01:00Z").start.year == 1970
    assert request(start="9999-12-30T23:59:00Z", end="9999-12-31T00:00:00Z").end.year == 9999


def test_numeric_string_tie_order_source_quote_sparse_buckets_and_units(tmp_path):
    path = partition(
        tmp_path,
        [
            (10, 0, "3", ".1", "7"),
            (2, 0, "2", ".2", "9"),
            (11, 59_999_999, "4", ".3", "11"),
            (12, 299_999_999, "6", "2", "12"),
        ],
    )
    bars = service(tmp_path)
    body = bars._query(request(), [selected(path)], threading.Event())
    assert body["returned_buckets"] == 2 and body["empty_buckets"] == 3
    first = body["bars"][0]
    assert first["open"] == "2.000000000000000000"
    assert first["close"] == "4.000000000000000000"
    assert first["base_volume"] == "0.600000000000000000"
    assert first["quote_volume"] == "27.000000000000000000"
    assert first["vwap"] == "45.000000000000000000"
    assert body["units"] == dict(price="USDT", quote_volume="USDT", base_volume="SOL")
    assert body["coverage_claim"] == "observed_only"
    assert valid_body(body, request(), [VERSION], metadata())


def test_non_usdt_units_from_registry_and_legacy_mixed_schema(tmp_path):
    path = partition(tmp_path, [(2, 0, "2", "1", "2")], identity="binance:spot:SOLBTC")
    meta = metadata("SOLBTC", "SOL", "BTC")
    req = request(instrument_id="binance:spot:SOLBTC")
    body = service(tmp_path)._query(
        req, [selected(path, identity=req.instrument_id, meta=meta)], threading.Event()
    )
    assert body["units"]["price"] == "BTC"
    legacy = partition(tmp_path, [(10, 60_000_000, "4", "2", "8")], name="legacy", legacy=True)
    # Trusted lower-level SQL projects shared trade columns from both schema layouts.
    rows = [selected(path), selected(legacy, version="c" * 64)]
    combined = service(tmp_path)._query(request(), rows, threading.Event())
    assert combined["returned_buckets"] == 2
    assert combined["bars"][1]["trade_count"] == 1


def test_five_minute_exactly_reconciles_minute_and_overflow_fails(tmp_path):
    path = partition(tmp_path, [(2, 0, "2", "1", "2"), (10, 60_000_000, "3", "2", "7")])
    bars = service(tmp_path)
    minute = bars._query(request(), [selected(path)], threading.Event())
    five = bars._query(request(interval="5m"), [selected(path)], threading.Event())
    assert five["bars"][0]["trade_count"] == sum(b["trade_count"] for b in minute["bars"])
    assert five["bars"][0]["quote_volume"] == "9.000000000000000000"
    overflow = partition(
        tmp_path,
        [(2, 0, "1", "99999999999999999999", "1"), (10, 1, "1", "99999999999999999999", "1")],
        name="overflow",
    )
    with pytest.raises(BarError, match="limits"):
        bars._query(request(), [selected(overflow)], threading.Event())


@pytest.mark.parametrize(
    "mutation",
    [
        lambda b: b.update(definition="bars-v1"),
        lambda b: b.update(schema="bars-v1"),
        lambda b: b.update(instrument_id="binance:spot:BTCUSDT"),
        lambda b: b["units"].update(base_volume="BTC"),
        lambda b: b["bars"][0].update(trade_count=True),
        lambda b: b["bars"][0].update(vwap="NaN"),
        lambda b: b.update(extra="unrecognized"),
    ],
)
def test_cache_validator_binds_schema_instrument_units_and_arithmetic(tmp_path, mutation):
    path = partition(tmp_path, [(2, 0, "2", "1", "2")])
    body = service(tmp_path)._query(request(), [selected(path)], threading.Event())
    mutation(body)
    assert not valid_body(body, request(), [VERSION], metadata())


def test_verified_bounds_and_inclusive_overlap_partitioned_by_instrument(tmp_path):
    path = partition(tmp_path, [(2, 0, "1", "1", "1"), (10, 1, "2", "1", "2")])
    assert numeric_bounds(path, threading.Event()) == (2, 10)
    rows = [
        dict(instrument_id=IDENTITY, id_bounds=(2, 10)),
        dict(instrument_id=IDENTITY, id_bounds=(10, 12)),
        dict(instrument_id=IDENTITY, id_bounds=(13, 20)),
        dict(instrument_id="binance:spot:BTCUSDT", id_bounds=(2, 10)),
    ]
    assert len(overlapping_groups(rows)) == 1 and len(overlapping_groups(rows)[0]) == 2


def test_exact_overlapping_merge_rejects_conflicts_and_accepts_agreement(tmp_path):
    a = partition(tmp_path, [(2, 0, "1", "1", "1"), (10, 1, "2", "1", "2")], name="a")
    b = partition(tmp_path, [(10, 1, "2", "1", "2"), (20, 2, "3", "1", "3")], name="b")
    rows = [selected(a), selected(b, version="b" * 64)]
    check_overlaps(rows, threading.Event())
    bad = partition(tmp_path, [(10, 1, "2", "1", "999")], name="bad")
    with pytest.raises(BarError, match="identities conflict"):
        check_overlaps([selected(a), selected(bad, version="c" * 64)], threading.Event())
    # Same numeric ID on another instrument is independent.
    check_overlaps([selected(a), selected(bad, identity="binance:spot:ETHUSDT")], threading.Event())


def test_disjoint_id_ranges_do_not_open_record_streams(tmp_path, monkeypatch):
    import marketlab.analytics.v2.bars as module

    monkeypatch.setattr(module, "_records", lambda *args: pytest.fail("disjoint scan opened"))
    check_overlaps(
        [
            dict(instrument_id=IDENTITY, id_bounds=(2, 10)),
            dict(instrument_id=IDENTITY, id_bounds=(11, 20)),
        ],
        threading.Event(),
    )


def test_cancelled_identity_merge_stops_and_query_drains(tmp_path):
    path = partition(tmp_path, [(2, 0, "1", "1", "1")])
    stop = threading.Event()
    stop.set()
    with pytest.raises(VerificationCancelled):
        check_overlaps([selected(path), selected(path)], stop)
    bars = service(tmp_path, query_timeout=0)
    with pytest.raises(BarError):
        bars._query(request(), [selected(path)], stop)
    assert bars.base.reader.compute.snapshot()["active"] == 0


def test_changed_prepared_signature_rejected_before_cache(tmp_path, monkeypatch):
    path = partition(tmp_path, [(2, 0, "1", "1", "1")])
    row = selected(path)
    bars = service(tmp_path)
    monkeypatch.setattr(bars, "_catalog", lambda versions: [dict(row, signature=(2,))])

    async def unexpected(*args):
        pytest.fail("cache accessed before binding check")

    monkeypatch.setattr(bars.base.cache, "get", unexpected)
    with pytest.raises(BarError, match="changed after verification"):
        asyncio.run(bars.read_prepared(request(), [row]))


def test_read_prepared_cache_and_close_do_not_close_shared_base(tmp_path, monkeypatch):
    path = partition(tmp_path, [(2, 0, "1", "1", "1")])
    row = selected(path)
    bars = service(tmp_path)
    monkeypatch.setattr(bars, "_catalog", lambda versions: [copy.deepcopy(row)])

    async def run():
        body, status = await bars.read_prepared(request(), [row])
        assert status == "BYPASS" and body["returned_buckets"] == 1
        await bars.close()
        assert bars.closed and not bars.base.closed
        await bars.base.close()

    asyncio.run(run())


def test_selection_rejects_missing_days_alternatives_and_quote_mismatch(tmp_path, monkeypatch):
    bars = service(tmp_path)
    day = START.date()
    row = dict(instrument_id=IDENTITY, trade_date=day, metadata=metadata())
    monkeypatch.setattr(bars, "_catalog", lambda versions: [row])
    with pytest.raises(BarError, match="coverage"):
        bars.resolve_selection(
            [IDENTITY], [VERSION], START, START + timedelta(days=2), threading.Event()
        )
    other = dict(
        instrument_id="binance:spot:BTCUSD",
        trade_date=day,
        metadata=metadata("BTCUSD", "BTC", "USD"),
    )
    monkeypatch.setattr(bars, "_catalog", lambda versions: [other, row])
    with pytest.raises(BarError, match="quote assets"):
        bars.resolve_selection(
            [IDENTITY, other["instrument_id"]],
            [VERSION, "c" * 64],
            START,
            START + timedelta(days=1),
            threading.Event(),
        )
    monkeypatch.setattr(bars, "_catalog", lambda versions: [row, dict(row)])
    with pytest.raises(BarError, match="coverage"):
        bars.resolve_selection(
            [IDENTITY], [VERSION, "c" * 64], START, START + timedelta(days=1), threading.Event()
        )


def test_changed_cached_id_proof_forces_full_content_reverification(tmp_path, monkeypatch):
    import marketlab.analytics.v2.bars as module

    path = partition(tmp_path, [(2, 0, "1", "1", "1")])
    row = selected(path)
    row.update(contract="dataset-manifest-v2", manifest_path=path.parent / "manifest.json")
    bars = service(tmp_path)
    bars.verified[VERSION] = dict(row, signature=(0,), manifest={})
    monkeypatch.setattr(bars, "_catalog", lambda versions: [dict(row)])
    called = []

    def reverify(*args, **kwargs):
        called.append(True)
        raise BarError("full reverification required")

    monkeypatch.setattr(module, "verify_dataset", reverify)
    with pytest.raises(BarError, match="full reverification"):
        bars.resolve_selection(
            [IDENTITY], [VERSION], START, START + timedelta(days=1), threading.Event()
        )
    assert called == [True]


def test_public_read_releases_shared_admission_if_owned_cleanup_fails(tmp_path, monkeypatch):
    from marketlab.datasets.v2.common import V2Error
    from marketlab.research.v2 import capacity

    bars = service(tmp_path)
    monkeypatch.setattr(capacity, "reserve", lambda *args, **kwargs: {"path": tmp_path})

    async def prepared(*args, **kwargs):
        return []

    async def read(*args, **kwargs):
        return {}, "BYPASS"

    def failed_cleanup(*args, **kwargs):
        raise V2Error("unavailable", "Owned cleanup failed")

    monkeypatch.setattr(bars, "prepare_selection", prepared)
    monkeypatch.setattr(bars, "read_prepared", read)
    monkeypatch.setattr(capacity, "release", failed_cleanup)
    with pytest.raises(V2Error, match="cleanup failed"):
        asyncio.run(bars._read(request()))
    assert bars.base.capacity._value == 2


def test_public_preparation_deadline_drains_then_releases_capacity(tmp_path, monkeypatch):
    from marketlab.research.v2 import capacity

    bars = service(tmp_path)
    bars.preparation_timeout = 0.01
    released = []
    stopped = []
    monkeypatch.setattr(capacity, "reserve", lambda *args, **kwargs: {"path": tmp_path})
    monkeypatch.setattr(capacity, "release", lambda *args, **kwargs: released.append(True))

    async def blocked(*args, **kwargs):
        try:
            await asyncio.sleep(10)
        finally:
            stopped.append(True)

    monkeypatch.setattr(bars, "prepare_selection", blocked)
    with pytest.raises(BarError, match="deadline") as caught:
        asyncio.run(bars._read(request()))
    assert caught.value.status == 504
    assert stopped == [True] and released == [True]
    assert bars.base.capacity._value == 2
