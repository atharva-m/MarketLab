"""V2 control validation is independent of legacy allowlists."""

from datetime import date

import pytest

from marketlab.datasets.v2.common import V2Error, canonical_json, date_value, parse_json
from marketlab.datasets.v2.core import canonical_metadata, official_request, registry_request


def registry(symbol: str = "SOLUSDT", base: str = "SOL") -> dict[str, object]:
    return dict(
        venue_id="binance",
        market="spot",
        source_symbol=symbol,
        base_asset=base,
        quote_asset="USDT",
        display_name=base + "/USDT",
        trade_id_order="numeric",
        adapter="binance_daily",
    )


def manifest() -> dict[str, object]:
    return dict(
        schema="canonical-trade-import-v1",
        instrument_id="binance:spot:SOLUSDT",
        trade_date="2025-03-01",
        format="csv",
        timestamp_encoding="rfc3339_utc",
        quote_quantity_mode="supplied",
        source_sha256="a" * 64,
        source_name="verified-export",
        source_reference=None,
        coverage_claim="observed_only",
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("venue_id", "poloniex"),
        ("market", "future"),
        ("trade_id_order", "utf8"),
        ("adapter", "canonical_file"),
    ],
)
def test_registry_rejects_unsupported_semantics(field: str, value: object) -> None:
    request = registry()
    request[field] = value
    with pytest.raises(V2Error):
        registry_request(request)


def test_registry_semantic_hash_excludes_label() -> None:
    a = registry()
    b = dict(a, display_name="Solana")
    assert registry_request(a)["semantic_sha256"] == registry_request(b)["semantic_sha256"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("format", []),
        ("timestamp_encoding", {}),
        ("source_sha256", None),
        ("trade_date", "2025-3-1"),
        ("instrument_id", "poloniex:spot:SOLUSDT"),
        ("quote_quantity_mode", "derived"),
    ],
)
def test_canonical_strict_values(field: str, value: object) -> None:
    value_dict = manifest()
    value_dict[field] = value
    with pytest.raises(V2Error):
        canonical_metadata(value_dict)


def test_json_duplicate_unknown_and_size() -> None:
    with pytest.raises(V2Error):
        parse_json(b'{"a":1,"a":2}')
    with pytest.raises(V2Error):
        parse_json(b'{"a":NaN}')
    with pytest.raises(V2Error):
        parse_json(b" " * 65537)
    request = manifest()
    request["remote_url"] = "https://example.invalid"
    with pytest.raises(V2Error):
        canonical_metadata(request)


def test_official_submission_cardinality() -> None:
    body = dict(
        schema="daily-ingestion-v2",
        adapter="binance_daily",
        instrument_ids=["binance:spot:ETHUSDT", "binance:spot:BTCUSDT"],
        from_date="2025-03-01",
        before_date="2025-04-01",
    )
    ids, first, before = official_request(body)
    assert ids == sorted(ids) and (before - first).days * len(ids) == 62
    body["before_date"] = "2025-04-02"
    with pytest.raises(V2Error):
        official_request(body)


def test_date_and_canonical_bytes() -> None:
    assert date_value("1970-01-01") == date(1970, 1, 1)
    assert canonical_json({"z": 2, "a": 1}) == b'{"a":1,"z":2}\n'
    with pytest.raises(V2Error):
        date_value("9999-12-31")


def test_exact_control_bytes_and_single_instrument_62_63() -> None:
    raw = b'{"a":1}'
    exact = raw + b" " * (65536 - len(raw))
    assert parse_json(exact) == {"a": 1}
    with pytest.raises(V2Error):
        parse_json(exact + b" ")
    request = dict(
        schema="daily-ingestion-v2",
        adapter="binance_daily",
        instrument_ids=["binance:spot:BTCUSDT"],
        from_date="2025-03-01",
        before_date="2025-05-02",
    )
    ids, first, before = official_request(request)
    assert (before - first).days * len(ids) == 62
    request["before_date"] = "2025-05-03"
    with pytest.raises(V2Error):
        official_request(request)


def test_exact_row_limit_counts_duplicates_before_collapse(tmp_path: object) -> None:
    from dataclasses import replace
    from pathlib import Path

    from marketlab.datasets.v2.common import DEFAULT_LIMITS, sha256_file
    from marketlab.datasets.v2.normalize import normalize_source

    root = Path(str(tmp_path))
    source = root / "one.csv"
    header = (
        "source_trade_id,executed_at,price,quantity,quote_quantity,is_buyer_maker,is_best_match\n"
    )
    record = "2,2025-03-01T00:00:00.000001Z,1,1,1,true,\n"
    source.write_text(header + record, encoding="utf-8")
    meta = dict(manifest(), source_sha256=sha256_file(source))
    inst = registry_request(registry())
    assert (
        normalize_source(
            source,
            root / "exact",
            metadata=meta,
            instrument=inst,
            limits=replace(DEFAULT_LIMITS, rows=1),
        )["accepted_rows"]
        == 1
    )
    source.write_text(header + record + record, encoding="utf-8")
    meta["source_sha256"] = sha256_file(source)
    with pytest.raises(V2Error):
        normalize_source(
            source,
            root / "one-over",
            metadata=meta,
            instrument=inst,
            limits=replace(DEFAULT_LIMITS, rows=1),
        )


@pytest.mark.parametrize("changed_id,changed_quote", [("3", "1"), ("2", "1.01")])
def test_provider_reference_comparison_detects_changed_ids_and_quotes(
    tmp_path: object, changed_id: str, changed_quote: str
) -> None:
    import hashlib
    from pathlib import Path

    from marketlab.datasets.v2.common import sha256_file
    from marketlab.datasets.v2.normalize import normalize_source

    root = Path(str(tmp_path))
    source = root / "reference-mutation.csv"
    source.write_text(
        "source_trade_id,executed_at,price,quantity,quote_quantity,"
        "is_buyer_maker,is_best_match\n"
        + f"{changed_id},2025-03-01T00:00:00.000001Z,1,1,{changed_quote},true,\n",
        encoding="utf-8",
    )
    metadata = dict(manifest(), source_sha256=sha256_file(source))
    quality = normalize_source(
        source, root / "normalized", metadata=metadata, instrument=registry_request(registry())
    )
    # Independent provider-reference row: a valid supplied file can differ from
    # the provider; reference verification must catch it, not claim authenticity.
    reference = (
        b'["binance:spot:SOLUSDT","2","2025-03-01T00:00:00.000001Z",'
        b'"1.000000000000000000","1.000000000000000000",'
        b'"1.000000000000000000",true,null]\n'
    )
    assert quality["logical_sha256"] != hashlib.sha256(reference).hexdigest()
