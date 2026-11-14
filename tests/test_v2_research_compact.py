"""Check the reduced physical envelope without a database or storage network."""

import hashlib
import io
import threading
from contextlib import nullcontext
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_v2_bars import START, partition, request, selected, service
from test_v2_research import body

from marketlab import workers
from marketlab.datasets.v2 import admission
from marketlab.datasets.v2.common import V2Error, canonical_json, digest
from marketlab.research.v2 import capacity, store
from marketlab.research.v2.numerics import calculate
from marketlab.research.v2.service import ResearchService
from marketlab.research.v2.spec import ResearchSpec
from marketlab.storage import materialize
from marketlab.storage.backend import ObjectRef, copy_verified


def member(length: int, *, version: str | None = "version-1") -> ObjectRef:
    return ObjectRef(
        "s3",
        "marketlab-phase7/frozen",
        version,
        length,
        "a" * 64,
        "trades.parquet",
        "application/vnd.apache.parquet",
    )


def test_compact_claim_checks_input_before_reducing_admission(monkeypatch, tmp_path):
    run_id = "fd254d02-ffcb-49cd-8d98-c819f2c02440"
    spec = ResearchSpec.create(body())
    dataset = {
        "contract": "dataset-manifest-v2",
        "dataset_version_id": spec.dataset_versions[0],
        "instrument_id": spec.instrument_ids[0],
        "manifest_sha256": "b" * 64,
    }
    fingerprint = {"datasets": [dataset], "request_sha256": spec.digest}
    fingerprint_sha = digest(fingerprint)
    engine = SimpleNamespace(connect=lambda: pytest.MonkeyPatch.context())
    monkeypatch.setattr(
        store,
        "one",
        lambda *a, **kw: {
            "fingerprint_json": canonical_json(fingerprint),
            "fingerprint_sha256": fingerprint_sha,
            "request_sha256": spec.digest,
            "spec_json": canonical_json(spec.body()),
        },
    )
    monkeypatch.setattr(admission, "root_for", lambda _: tmp_path)
    observed = []

    def acquire(_engine, root, role, logical, *, physical_bytes):
        observed.append((root, role, logical, physical_bytes))
        return {"ticket_id": "exclusive"}

    monkeypatch.setattr(admission, "acquire", acquire)
    monkeypatch.setattr(store, "_claim", lambda *args: store.Claim(run_id, "owner", 1, 1))
    monkeypatch.setattr(materialize, "registered_members", lambda *args: (member(4 * 1024**2 + 1),))
    with pytest.raises(V2Error, match="private scratch limit"):
        store.claim(engine, {}, run_id, compact_fingerprint=fingerprint_sha)
    assert not observed
    local = ObjectRef(
        "local",
        "marketlab-phase7/frozen",
        None,
        6200,
        "a" * 64,
        "trades.parquet",
        "application/vnd.apache.parquet",
    )
    monkeypatch.setattr(materialize, "registered_members", lambda *args: (local,))
    with pytest.raises(V2Error, match="private scratch limit"):
        store.claim(engine, {}, run_id, compact_fingerprint=fingerprint_sha)
    assert not observed
    with pytest.raises(V2Error, match="pinned run fingerprint"):
        store.claim(engine, {}, run_id, compact_fingerprint="f" * 64)
    assert not observed
    monkeypatch.setattr(
        materialize, "registered_members", lambda *args: (member(6200, version=None),)
    )
    with pytest.raises(V2Error, match="private scratch limit"):
        store.claim(engine, {}, run_id, compact_fingerprint=fingerprint_sha)
    assert not observed
    monkeypatch.setattr(materialize, "registered_members", lambda *args: (member(6200),))
    assert store.claim(engine, {}, run_id, compact_fingerprint=fingerprint_sha) is not None
    assert store.claim(engine, {}, run_id) is not None
    assert observed == [
        (tmp_path, "research", 1024**2, 2 * 1024**3 + 9 * 1024**2),
        (
            tmp_path,
            "research",
            capacity.OUTPUT,
            capacity.SCRATCH + capacity.SPILL + capacity.OUTPUT,
        ),
    ]


def test_compact_locked_fingerprint_failure_finishes_ticket_without_attempt(monkeypatch, tmp_path):
    run = "fd254d02-ffcb-49cd-8d98-c819f2c02440"
    ticket = {"ticket_id": "exclusive"}
    seen = []
    finished = []
    engine = SimpleNamespace(connect=lambda: pytest.MonkeyPatch.context())
    monkeypatch.setattr(admission, "root_for", lambda _: tmp_path)
    monkeypatch.setattr(admission, "acquire", lambda *args, **kwargs: ticket)
    monkeypatch.setattr(
        admission, "finish", lambda _engine, current, size: finished.append((current, size))
    )
    monkeypatch.setattr(store, "_check_compact_storage", lambda *_: None)
    monkeypatch.setattr(store, "transaction", lambda _: pytest.MonkeyPatch.context())
    monkeypatch.setattr(workers, "guard", lambda *_: None)
    monkeypatch.setattr(
        store, "execute", lambda *args, **kwargs: pytest.fail("attempt was written")
    )
    monkeypatch.setattr(store, "one", lambda *_args, **_kwargs: {"run_id": run})

    def verify(_connection, run_id, fingerprint):
        seen.append((run_id, fingerprint))
        if len(seen) == 2:
            raise V2Error("invalid_request", "locked fingerprint changed")
        return {}

    monkeypatch.setattr(store, "_compact_input", verify)
    execution = {
        key: "pinned" for key in ("source_sha256", "lock_sha256", "numerics", "bars", "inventory")
    }
    with pytest.raises(V2Error, match="locked fingerprint changed"):
        store.claim(engine, execution, run, compact_fingerprint="a" * 64)
    assert seen == [(run, "a" * 64)] * 2
    assert finished == [(ticket, 0)]


def test_compact_cold_materialized_parquet_keeps_default_numerics(monkeypatch, tmp_path):
    records = [(i + 1, i * 300_000_000, "2", "1", "2") for i in range(20)]
    parquet = partition(tmp_path, records)
    raw = parquet.read_bytes()
    reference = ObjectRef(
        "s3",
        "marketlab-phase7/frozen",
        "ver-1",
        len(raw),
        hashlib.sha256(raw).hexdigest(),
        "trades.parquet",
        "application/vnd.apache.parquet",
    )
    cache = materialize.FileCache()
    bounded = tmp_path / "owned"
    bounded.mkdir()
    bars = service(tmp_path)
    stop = threading.Event()
    req = request(interval="5m", end=START + timedelta(minutes=100))
    row = selected(parquet)
    expected = bars._query(req, [row], stop)
    copy = SimpleNamespace(
        read_verified=lambda ref, target, **opts: copy_verified(
            io.BytesIO(raw), target, ref, **opts
        )
    )
    monkeypatch.setattr(materialize, "backend_for", lambda *_: copy)
    monkeypatch.setattr(materialize, "managed_backend", nullcontext)

    def no_hardlinks(*_):
        raise OSError("Hardlink fallback test")

    monkeypatch.setattr(materialize, "os", SimpleNamespace(link=no_hardlinks))
    monkeypatch.setattr(
        materialize,
        "reserve_space",
        lambda *_a, **_kw: pytest.fail("compact path allocated a shared cache"),
    )
    scratch = materialize.Scratch(directory=bounded, limit=2 * len(raw), private=True)
    with cache.package(None, tmp_path, (reference,), scratch) as workspace:
        assert scratch.used == 2 * len(raw)
        assert (workspace / "trades.parquet").read_bytes() == raw
    assert scratch.used == 0
    monkeypatch.setattr("marketlab.analytics.v2.bars.CACHE", cache)
    compact = bars._query(req, [{**row, "refs": (reference,)}], stop, bounded, 2 * len(raw))
    assert compact == expected
    spec = ResearchSpec.create(body())
    fingerprint = {"request_sha256": spec.digest}
    claim = store.Claim("run", "owner", 1, 1)
    for outcome, output_limit in (
        (expected, None),
        (compact, capacity.SMALL_RESEARCH_SPACE.output),
    ):
        values = calculate(
            spec,
            {spec.instrument_ids[0]: outcome["bars"]},
            {spec.instrument_ids[0]: row["metadata"]},
            stop,
        )
        staged = ResearchService.stage(
            None, claim, spec, fingerprint, *values, bounded, output_limit=output_limit
        )
        hashes = {
            name: hashlib.sha256((staged / name).read_bytes()).hexdigest()
            for name in ("spec.json", "results.json", "summary.json")
        }
        if output_limit is None:
            expected_hashes = hashes
        else:
            assert hashes == expected_hashes


def test_private_materialization_guards_combined_bytes_before_copy(tmp_path):
    cache = materialize.FileCache()
    scratch = materialize.Scratch(used=8, directory=tmp_path, limit=10, private=True)
    backend = SimpleNamespace(
        read_verified=lambda *args, **kwargs: pytest.fail("read exceeded cap")
    )
    with (
        pytest.raises(V2Error, match="scratch limit"),
        cache._pin_backend(None, tmp_path, member(3), scratch, None, backend),
    ):
        pass
    assert scratch.used == 8
    assert not list(tmp_path.iterdir())


def test_compact_publication_refuses_manifest_past_aggregate_cap(monkeypatch, tmp_path):
    monkeypatch.setattr("marketlab.research.v2.service.verify_directory", lambda *args: None)
    spec = ResearchSpec.create(body())
    claim = store.Claim("run", "owner", 1, 1)
    arguments = (claim, spec, {"request_sha256": spec.digest}, {}, {})
    output = ResearchService.stage(None, *arguments, tmp_path)
    size = sum(path.stat().st_size for path in output.iterdir())
    assert ResearchService.stage(None, *arguments, tmp_path, output_limit=size).is_dir()
    with pytest.raises(V2Error, match="manifest exceeds limit"):
        ResearchService.stage(None, *arguments, tmp_path, output_limit=size - 1)
    partial = [path for path in tmp_path.iterdir() if not (path / "manifest.json").exists()]
    assert len(partial) == 1
    assert {path.name for path in Path(partial[0]).iterdir()} == {
        "spec.json",
        "results.json",
        "summary.json",
    }
