"""Local verification and pinning regressions for registered artifacts."""

import hashlib
import tempfile
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from marketlab.datasets.normalize import VerificationCancelled
from marketlab.datasets.v2.common import V2Error
from marketlab.storage import materialize
from marketlab.storage.backend import ObjectRef
from marketlab.storage.materialize import FileCache, Scratch


@pytest.fixture
def engine(monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    # Materialization's authoritative bytes are real local files. Replace only
    # the separate PostgreSQL physical ledger in this focused offline test.
    monkeypatch.setattr(materialize, "reserve_space", offline_space)
    db = sa.create_engine("sqlite://")
    try:
        yield db
    finally:
        db.dispose()


def offline_space(engine: Engine, root: Path, amount: int, **kwargs: bool) -> SimpleNamespace:
    folder = tempfile.TemporaryDirectory(dir=root)
    return SimpleNamespace(
        engine=engine, path=Path(folder.name), close=folder.cleanup, grow=lambda _: None
    )


def artifact(root: Path, key: str, data: bytes, member: str = "manifest.json") -> ObjectRef:
    (root / key).write_bytes(data)
    return ObjectRef(
        "local", key, None, len(data), hashlib.sha256(data).hexdigest(), member, "application/json"
    )


def test_poison_refetches_exact_local_member_and_missing_authority_fails(
    tmp_path: Path, engine: Engine
) -> None:
    ref = artifact(tmp_path, "member", b"original")
    cache = FileCache()
    with cache.pin(engine, tmp_path, ref, Scratch()) as path:
        path.write_bytes(b"poisoned")
    with cache.package(engine, tmp_path, (ref,), Scratch()) as directory:
        assert (directory / "manifest.json").read_bytes() == b"original"
    assert not directory.exists()
    (tmp_path / ref.key).unlink()
    with pytest.raises(V2Error, match="missing"), cache.pin(engine, tmp_path, ref, Scratch()):
        pytest.fail("authoritative file was absent")
    cache.close()


def test_pinned_entry_uses_bounded_scratch_and_releases_for_eviction(
    tmp_path: Path, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(materialize, "SCRATCH", 4)
    first = artifact(tmp_path, "first", b"1234")
    second = artifact(tmp_path, "second", b"abcd")
    third = artifact(tmp_path, "third", b"efgh")
    cache = FileCache(limit=4)
    scratch = Scratch()
    with (
        cache.pin(engine, tmp_path, first, scratch) as pinned,
        cache.pin(engine, tmp_path, second, scratch) as transient,
    ):
        assert scratch.used == 4
        assert pinned.read_bytes() == b"1234"
        with (
            pytest.raises(V2Error, match="scratch limit"),
            cache.pin(engine, tmp_path, third, scratch),
        ):
            pytest.fail("pinned capacity was exceeded")
    assert scratch.used == 0 and not transient.exists()
    with cache.pin(engine, tmp_path, third, scratch) as path:
        assert not pinned.exists() and path.read_bytes() == b"efgh"
    cache.close()


def test_cancelled_materialization_leaves_no_reusable_partial(
    tmp_path: Path, engine: Engine
) -> None:
    ref = artifact(tmp_path, "member", b"verified")
    cache = FileCache()
    checks = iter((False, True))
    with (
        pytest.raises((VerificationCancelled, V2Error)),
        cache.pin(engine, tmp_path, ref, Scratch(), lambda: next(checks, True)),
    ):
        pytest.fail("cancelled materialization was exposed")
    with cache.pin(engine, tmp_path, ref, Scratch()) as path:
        assert path.read_bytes() == b"verified"
    cache.close()
