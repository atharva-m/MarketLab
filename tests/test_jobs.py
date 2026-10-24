"""Offline R2 request bounds, worker bounds and retry classification."""

from datetime import date, datetime
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
from sqlalchemy.engine import Engine

from marketlab.datasets import DatasetError
from marketlab.datasets.jobs import validate_request, work
from marketlab.datasets.source import TransientSourceError, download_archive

JAN = date(2025, 1, 1)
FEB = date(2025, 2, 1)


@pytest.mark.parametrize(
    ("symbols", "start", "before", "key"),
    [
        ([], JAN, FEB, "key"),
        (["BTCUSDT", "BTCUSDT"], JAN, FEB, "key"),
        (["BTCUSDT", "ETHUSDT", "XRPUSDT"], JAN, FEB, "key"),
        (["btcusdt"], JAN, FEB, "key"),
        (["XRPUSDT"], JAN, FEB, "key"),
        (["BTCUSDT"], date(2024, 12, 31), FEB, "key"),
        (["BTCUSDT"], JAN, date(2025, 2, 2), "key"),
        (["BTCUSDT"], JAN, JAN, "key"),
        (["BTCUSDT"], FEB, JAN, "key"),
        (["BTCUSDT"], datetime(2025, 1, 1), FEB, "key"),
        (["BTCUSDT"], JAN, FEB, ""),
        (["BTCUSDT"], JAN, FEB, "a" * 129),
        (["BTCUSDT"], JAN, FEB, "../escape"),
        (["BTCUSDT"], JAN, FEB, "secret\nkey"),
        (["BTCUSDT"], JAN, FEB, "é"),
    ],
)
def test_request_rejects_invalid_shape_before_database(symbols, start, before, key) -> None:
    with pytest.raises(DatasetError):
        validate_request(symbols, start, before, key)


def test_request_canonicalizes_symbols_and_accepts_month() -> None:
    assert validate_request(["ETHUSDT", "BTCUSDT"], JAN, FEB, "R2.month-1") == [
        "BTCUSDT",
        "ETHUSDT",
    ]


@pytest.mark.parametrize("maximum,wait", [(0, 0), (63, 0), (True, 0), (1, -1), (1, 3601)])
def test_worker_bounds_rejected_without_database(maximum: int, wait: int) -> None:
    engine = Mock(spec=Engine)
    with pytest.raises(DatasetError):
        work(engine, Mock(), max_jobs=maximum, wait_seconds=wait)
    engine.begin.assert_not_called()


@pytest.mark.parametrize("status", [408, 429, 500, 503])
def test_transient_http_failure_has_bounded_retry_and_no_hidden_retries(
    tmp_path: Path, status: int
) -> None:
    calls = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request.url)
        return httpx.Response(status, headers={"Retry-After": "99999"})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(TransientSourceError) as caught:
            download_archive(client, tmp_path, symbol="BTCUSDT", trade_date=JAN)
    assert caught.value.retry_after == 3600
    assert len(calls) == 1


@pytest.mark.parametrize("status", [301, 400, 403, 404])
def test_permanent_http_failure_is_not_transient(tmp_path: Path, status: int) -> None:
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(status))) as client:
        with pytest.raises(DatasetError) as caught:
            download_archive(client, tmp_path, symbol="ETHUSDT", trade_date=JAN)
    assert not isinstance(caught.value, TransientSourceError)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("0", 0),
        ("120", 120),
        ("999999", 3600),
        ("9" * 129, 0),
        ("-1", 0),
        ("1.5", 0),
        ("invalid", 0),
        ("١٢", 0),
        ("Wed, 01 Jan 2020 00:00:00 GMT", 0),
        ("Wed, 01 Jan 2030 00:00:00", 0),
    ],
)
def test_retry_after_delta_invalid_past_and_unzoned_values(value: str, expected: int) -> None:
    from marketlab.datasets.source import retry_after_seconds

    assert retry_after_seconds(value) == expected


@pytest.mark.parametrize("delay,expected", [(120, 120), (7200, 3600)])
def test_retry_after_http_date_is_accepted_and_bounded(
    delay: int, expected: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import UTC, timedelta
    from email.utils import format_datetime

    from marketlab.datasets import source

    fixed = datetime(2026, 10, 24, tzinfo=UTC)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed

    monkeypatch.setattr(source, "datetime", FrozenDateTime)
    assert (
        source.retry_after_seconds(format_datetime(fixed + timedelta(seconds=delay), usegmt=True))
        == expected
    )
