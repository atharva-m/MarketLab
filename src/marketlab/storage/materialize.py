"""Pinned, bounded local views of exact registered artifact members."""

import atexit
import hashlib
import logging
import os
import tempfile
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Iterator, Mapping
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from marketlab.datasets.normalize import VerificationCancelled
from marketlab.datasets.v2.capacity import SCRATCH
from marketlab.datasets.v2.common import V2Error
from marketlab.storage.backend import (
    Backend,
    ObjectRef,
    backend_for,
    copy_verified,
    managed_backend,
)
from marketlab.storage.materialize_space import MaterializationSpace, reserve_space

CACHE_BYTES = 10 * 1024**3
READ_SECONDS = 1800
DATASET_MEMBERS = {"manifest.json": 1024**2, "trades.parquet": 4 * 1024**3}
V2_DATASET_MEMBERS = DATASET_MEMBERS | {"manifest.json": 64 * 1024, "quality.json": 64 * 1024}
_OPERATOR_VERIFY = ContextVar("materialization_operator_verification", default=False)


@contextmanager
def without_cache() -> Iterator[None]:
    """Use transient reservations during an explicit quiescent reconciliation."""
    token = _OPERATOR_VERIFY.set(True)
    try:
        yield
    finally:
        _OPERATOR_VERIFY.reset(token)


def registered_members(
    engine: Engine,
    root: Path,
    owner: str,
    owner_id: str,
    limits: Mapping[str, int],
    manifest_hash: str,
) -> tuple[ObjectRef, ...] | None:
    from marketlab.storage.store import get_registered, media_schema

    refs = get_registered(engine, owner, owner_id, root=root)
    if refs is None:
        return None
    if len(refs) != len(limits) or {ref.member for ref in refs} != limits.keys():
        raise V2Error("integrity_failure", "Registered artifact member set is invalid")
    for ref in refs:
        if (
            not 1 <= ref.length <= limits[ref.member]
            or ref.media_schema != media_schema(Path(ref.member))
            or (ref.member == "manifest.json" and ref.sha256 != manifest_hash)
        ):
            raise V2Error("integrity_failure", "Registered artifact member is invalid")
    return refs


def check_registered(
    root: Path, refs: tuple[ObjectRef, ...], cancelled: Callable[[], bool] | None = None
) -> None:
    for ref in refs:
        if cancelled is not None and cancelled():
            raise VerificationCancelled("Artifact verification stopped")
        with managed_backend(backend_for(root, ref.alias)) as backend:
            backend.stat(ref)
    if cancelled is not None and cancelled():
        raise VerificationCancelled("Artifact verification stopped")


@dataclass
class Scratch:
    """Materialized scratch plus any bytes held by a caller's current working files."""

    used: int = 0
    directory: Path | None = None


@dataclass
class _Entry:
    path: Path
    space: MaterializationSpace
    pins: int = 0
    corrupt: bool = False


class FileCache:
    def __init__(self, limit: int = CACHE_BYTES) -> None:
        self.limit = limit
        self._lock = threading.Lock()
        self._entries: OrderedDict[tuple[str, int], _Entry] = OrderedDict()
        self._inflight: set[tuple[str, int]] = set()
        self._charged = 0

    def _evict(self, key: tuple[str, int], entry: _Entry) -> None:
        entry.space.close()
        del self._entries[key]
        self._charged -= key[1]

    def close(self, engine: Engine | None = None) -> None:
        with self._lock:
            for key, entry in tuple(self._entries.items()):
                if not entry.pins and (engine is None or entry.space.engine is engine):
                    self._evict(key, entry)

    def _make_room(self, length: int) -> bool:
        if length > self.limit:
            return False
        for key in tuple(self._entries):
            if self._charged + length <= self.limit:
                break
            entry = self._entries[key]
            if not entry.pins:
                self._evict(key, entry)
        return self._charged + length <= self.limit

    @staticmethod
    def _valid(path: Path, ref: ObjectRef, check: Callable[[], None]) -> bool:
        try:
            if path.is_symlink() or not path.is_file() or path.stat().st_size != ref.length:
                return False
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024**2), b""):
                    check()
                    digest.update(block)
            return digest.hexdigest() == ref.sha256
        except OSError:
            return False

    def _unpin(self, key: tuple[str, int], entry: _Entry, *, corrupt: bool = False) -> None:
        with self._lock:
            entry.pins -= 1
            entry.corrupt |= corrupt
            if entry.corrupt and entry.pins == 0:
                self._evict(key, entry)

    @contextmanager
    def pin(
        self,
        engine: Engine,
        root: Path,
        ref: ObjectRef,
        scratch: Scratch,
        cancelled: Callable[[], bool] | None = None,
    ) -> Iterator[Path]:
        with (
            managed_backend(backend_for(root, ref.alias)) as backend,
            self._pin_backend(engine, root, ref, scratch, cancelled, backend) as path,
        ):
            yield path

    @contextmanager
    def _pin_backend(
        self,
        engine: Engine,
        root: Path,
        ref: ObjectRef,
        scratch: Scratch,
        cancelled: Callable[[], bool] | None,
        backend: Backend,
    ) -> Iterator[Path]:
        deadline = time.monotonic() + READ_SECONDS

        def stopped() -> bool:
            return time.monotonic() >= deadline or (cancelled is not None and cancelled())

        def check() -> None:
            if stopped():
                raise VerificationCancelled("Artifact materialization stopped")

        check()
        key = (ref.sha256, ref.length)
        with self._lock:
            entry = None if _OPERATOR_VERIFY.get() else self._entries.get(key)
            if entry is not None and not entry.corrupt:
                entry.pins += 1
                self._entries.move_to_end(key)
            else:
                entry = None
        if entry is not None:
            valid = True
            try:
                backend.stat(ref)
                check()
                valid = self._valid(entry.path, ref, check)
                if valid:
                    yield entry.path
                    return
            finally:
                self._unpin(key, entry, corrupt=not valid)

        with self._lock:
            cacheable = (
                not _OPERATOR_VERIFY.get()
                and key not in self._inflight
                and key not in self._entries
                and self._make_room(ref.length)
            )
            if cacheable:
                self._inflight.add(key)
                self._charged += ref.length
        if not cacheable:
            with self._temporary_member(engine, root, ref, scratch, stopped, backend) as path:
                check()
                yield path
            return

        space = None
        installed = False
        try:
            try:
                space = reserve_space(engine, root, ref.length)
            except V2Error as error:
                if error.code != "capacity_exceeded" or scratch.directory is None:
                    raise
                with self._temporary_member(engine, root, ref, scratch, stopped, backend) as path:
                    check()
                    yield path
                return
            path = space.path / "content"
            with path.open("xb") as stream:
                backend.read_verified(ref, stream, cancelled=stopped)
            check()
            with self._lock:
                entry = self._entries[key] = _Entry(path, space, 1)
                installed = True
            yield path
        finally:
            with self._lock:
                self._inflight.remove(key)
                if not installed:
                    self._charged -= ref.length
            if installed:
                assert entry is not None
                self._unpin(key, entry)
            elif space is not None:
                space.close()

    @contextmanager
    def _temporary_member(
        self,
        engine: Engine,
        root: Path,
        ref: ObjectRef,
        scratch: Scratch,
        cancelled: Callable[[], bool],
        backend: Backend,
    ) -> Iterator[Path]:
        if scratch.used + ref.length > SCRATCH:
            raise V2Error("capacity_exceeded", "Artifact materialization exceeds scratch limit")
        scratch.used += ref.length
        try:
            with materialization_workspace(engine, root, ref.length, owned=scratch.directory) as (
                directory,
                _,
            ):
                path = directory / "content"
                with path.open("xb") as stream:
                    backend.read_verified(ref, stream, cancelled=cancelled)
                yield path
        finally:
            scratch.used -= ref.length

    @contextmanager
    def _copy_for_view(
        self,
        source: Path,
        destination: Path,
        ref: ObjectRef,
        scratch: Scratch,
        cancelled: Callable[[], bool] | None,
    ) -> Iterator[None]:
        if scratch.used + ref.length > SCRATCH:
            raise V2Error("capacity_exceeded", "Artifact package view exceeds scratch limit")
        scratch.used += ref.length
        try:
            with source.open("rb") as original, destination.open("xb") as view:
                copy_verified(original, view, ref, cancelled=cancelled)
            yield
        finally:
            scratch.used -= ref.length

    @contextmanager
    def package(
        self,
        engine: Engine,
        root: Path,
        refs: tuple[ObjectRef, ...],
        scratch: Scratch,
        cancelled: Callable[[], bool] | None = None,
        *,
        children_pending: bool = False,
    ) -> Iterator[Path]:
        with (
            ExitStack() as pins,
            materialization_workspace(
                engine, root, 0, owned=scratch.directory, children_pending=children_pending
            ) as (target, space),
        ):
            for ref in refs:
                member = pins.enter_context(self.pin(engine, root, ref, scratch, cancelled))
                destination = target / ref.member
                # Inventory counts by pathname. Hold conservative coverage for
                # the view name even when it shares its source cache inode.
                if space is not None:
                    space.grow(ref.length)
                try:
                    os.link(member, destination)
                except OSError:
                    pins.enter_context(
                        self._copy_for_view(member, destination, ref, scratch, cancelled)
                    )
            yield target


CACHE = FileCache()


@atexit.register
def _close_process_cache() -> None:
    try:
        CACHE.close()
    except (OSError, V2Error, SQLAlchemyError):
        logging.getLogger(__name__).warning("Materialization cleanup incomplete; reservations held")


@contextmanager
def materialization_workspace(
    engine: Engine,
    root: Path,
    amount: int,
    *,
    owned: Path | None = None,
    children_pending: bool = False,
) -> Iterator[tuple[Path, MaterializationSpace | None]]:
    if owned is not None:
        # The caller holds the existing SCRATCH reservation through native drain.
        with tempfile.TemporaryDirectory(prefix="materialize-", dir=owned) as directory:
            yield Path(directory), None
        return
    space = reserve_space(
        engine,
        root,
        amount,
        allow_unready=_OPERATOR_VERIFY.get(),
        children_pending=children_pending,
    )
    try:
        yield space.path, space
    finally:
        space.close()


@contextmanager
def materialize_package(
    engine: Engine,
    root: Path,
    refs: tuple[ObjectRef, ...] | None,
    implicit: Callable[[], Path] | Path,
    *,
    scratch: Scratch | None = None,
    cancelled: Callable[[], bool] | None = None,
    children_pending: bool = False,
) -> Iterator[Path]:
    if refs is None:
        yield implicit() if callable(implicit) else implicit
        return
    with CACHE.package(
        engine, root, refs, scratch or Scratch(), cancelled, children_pending=children_pending
    ) as directory:
        yield directory
