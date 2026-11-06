"""Bounded generation-scoped browser transport feeding the existing durable jobs."""

import asyncio
import hashlib
import hmac
import os
import secrets
import threading
from datetime import timedelta
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from sqlalchemy.engine import Engine
from starlette.requests import Request

from . import admission, jobs, native_identity
from .common import (
    DEFAULT_LIMITS,
    V2Error,
    canonical_json,
    date_value,
    exact_fields,
    safe_path,
    sha256_file,
)
from .core import (
    canonical_metadata,
    execute,
    instrument,
    lock,
    metadata_hash,
    one,
    operation,
    save_operation,
    transaction,
    uid,
    wire,
)


def _revision(body: dict[str, Any], finalize: bool = False) -> int:
    exact_fields(body, {"expected_revision", "generation"} if finalize else {"expected_revision"})
    value = body["expected_revision"]
    if type(value) is not int or value < 0:
        raise V2Error("invalid_request", "Invalid expected revision")
    if finalize:
        uid(body["generation"])
    return value


async def _io(function: Any, *args: Any, **kwargs: Any) -> Any:
    """Cancellation stops awaiting only after this exact executor task drains."""
    task = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
    result = task.result()
    if cancelled:
        raise asyncio.CancelledError
    return result


def _signature(path: Path) -> tuple[int, int, int, int]:
    stat = path.stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns


class BrowserImports:
    def __init__(self, engine: Engine, root: Path) -> None:
        self.engine, self.root = engine, admission.safe_root(root)
        self._streams: dict[str, threading.Event] = {}
        self._streams_lock = threading.Lock()

    def _current(self, connection: Any, identity: str, *, locked: bool = False) -> dict[str, Any]:
        row = one(
            connection,
            "SELECT * FROM v2_canonical_imports WHERE import_id=:id "
            "AND transport='browser'" + (" FOR UPDATE" if locked else ""),
            id=uid(identity),
        )
        if row is None:
            raise V2Error("not_found", "Browser import not found")
        return row

    def inspect(self, identity: str) -> dict[str, Any]:
        self.recover(identity)
        with self.engine.connect() as connection:
            row = self._current(connection, identity)
            job = one(
                connection,
                "SELECT job_id,result_version FROM v2_ingestion_jobs WHERE import_id=:id",
                id=row["import_id"],
            )
            generation = one(
                connection,
                "SELECT expires_at FROM v2_upload_generations WHERE generation_id=:id",
                id=row["generation_id"],
            )
        return cast(
            dict[str, Any],
            wire(
                {
                    "id": row["import_id"],
                    "state": row["state"],
                    "revision": row["revision"],
                    "declared_bytes": row["declared_bytes"],
                    "received_bytes": row["received_bytes"],
                    "source_sha256": row["source_sha256"],
                    "generation": row["generation_id"],
                    "generation_expires_at": None
                    if generation is None
                    else generation["expires_at"],
                    "submission_id": row["submission_id"],
                    "job_id": None if job is None else job["job_id"],
                    "dataset_version_id": None if job is None else job["result_version"],
                    "error": None
                    if row["error_code"] is None
                    else {"code": row["error_code"], "message": "Import requires attention."},
                }
            ),
        )

    def create(self, body: dict[str, Any], key: str) -> dict[str, Any]:
        exact_fields(body, {"manifest", "content_length"})
        if not isinstance(body["manifest"], dict):
            raise V2Error("invalid_request", "Canonical manifest object required")
        metadata = canonical_metadata(body["manifest"])
        size = body["content_length"]
        if type(size) is not int or not 1 <= size <= DEFAULT_LIMITS.source_bytes:
            raise V2Error("invalid_request", "Invalid canonical file length")
        with transaction(self.engine) as connection:
            old = operation(connection, "browser-create", key, body)
            if old is not None:
                return old
            admission.require(connection, self.root)
        identity = str(uuid4())
        ticket = admission.acquire(
            self.engine, self.root, "upload", size, identity, physical_bytes=size
        )
        if ticket is None:
            raise V2Error("unavailable", "Storage initialization required")
        try:
            with transaction(self.engine) as connection:
                old = operation(connection, "browser-create", key, body)
                if old is not None:
                    result = old
                else:
                    current = instrument(connection, metadata["instrument_id"], enabled=True)
                    generation = uuid4()
                    relative = f"staging-v2/{identity}/{generation}/source.{metadata['format']}"
                    execute(
                        connection,
                        "INSERT INTO v2_canonical_imports "
                        "(import_id,instrument_id,semantic_sha256,trade_date,metadata_json,metadata_sha256,"
                        "source_sha256,format,declared_bytes,received_bytes,generation_id,source_relative_path,"
                        "state,revision,created_at,updated_at,transport) VALUES "
                        "(:id,:instrument,:semantic,:day,CAST(:metadata AS jsonb),"
                        ":msha,:sha,:format,:size,0,"
                        ":generation,:path,'awaiting_upload',0,clock_timestamp(),clock_timestamp(),'browser')",
                        id=identity,
                        instrument=current["instrument_id"],
                        semantic=current["semantic_sha256"],
                        day=date_value(metadata["trade_date"]),
                        metadata=canonical_json(metadata).decode(),
                        msha=metadata_hash(metadata),
                        sha=metadata["source_sha256"],
                        format=metadata["format"],
                        size=size,
                        generation=generation,
                        path=relative,
                    )
                    result = self._generation(
                        connection,
                        identity,
                        generation,
                        relative,
                        size,
                        metadata["source_sha256"],
                        1,
                        ticket,
                    )
                    result.update(id=identity, state="awaiting_upload", revision=0)
                    admission.activate(connection, ticket, identity, generation=generation)
                    result = save_operation(connection, "browser-create", key, body, result)
            if result["id"] != identity:
                admission.finish(self.engine, ticket, 0)
            return result
        except BaseException:
            admission.finish(self.engine, ticket, 0)
            raise

    def _generation(
        self,
        connection: Any,
        identity: str,
        generation: Any,
        relative: str,
        size: int,
        sha: str,
        ordinal: int,
        ticket: dict[str, Any],
    ) -> dict[str, Any]:
        # acquire() reserved these physical bytes under the root lock BEFORE
        # the import row. Atomically transfer that budget without acquiring the
        # root lock while holding the import. MVCC exposes either ticket or
        # source-ledger reservation, never an uncharged interval.
        transferred = execute(
            connection,
            "UPDATE v2_admission_tickets SET "
            "physical_bytes=physical_bytes-:bytes WHERE ticket_id=:id AND owner=:owner "
            "AND physical_bytes>=:bytes AND state IN ('pending','active') RETURNING ticket_id",
            bytes=size,
            id=ticket["ticket_id"],
            owner=ticket["owner"],
        ).first()
        if transferred is None:
            raise V2Error("ownership_lost", "Upload physical reservation unavailable")
        execute(
            connection,
            "INSERT INTO v2_storage_reservations VALUES "
            "(:id,:import_id,NULL,NULL,'source',:bytes,0,:bytes,'reserved',:path,"
            "clock_timestamp(),clock_timestamp())",
            id=uuid4(),
            import_id=identity,
            bytes=size,
            path=relative,
        )
        reservation = one(
            connection,
            "SELECT reservation_id FROM v2_storage_reservations WHERE relative_path=:path",
            path=relative,
        )
        assert reservation is not None
        from marketlab.storage.store import enabled

        if enabled(connection):
            execute(
                connection,
                "UPDATE v2_storage_reservations SET data_charge_id=:charge "
                "WHERE reservation_id=:id",
                charge=ticket["charge_id"],
                id=reservation["reservation_id"],
            )
        token = secrets.token_urlsafe(32)
        row = one(
            connection,
            "INSERT INTO v2_upload_generations VALUES "
            "(:generation,:import_id,:ordinal,:path,:token,clock_timestamp()+interval '15 minutes',"
            "NULL,NULL,:bytes,0,:sha,'issued',:reservation,:ticket,:charge,"
            "clock_timestamp(),clock_timestamp()) "
            "RETURNING expires_at",
            generation=generation,
            import_id=identity,
            ordinal=ordinal,
            path=relative,
            token=hashlib.sha256(token.encode()).hexdigest(),
            bytes=size,
            sha=sha,
            reservation=reservation["reservation_id"],
            ticket=ticket["ticket_id"],
            charge=ticket["charge_id"],
        )
        assert row is not None
        return cast(
            dict[str, Any],
            wire(
                {
                    "upload": {
                        "method": "PUT",
                        "url": f"/v2/imports/{identity}/content",
                        "generation": generation,
                        "expires_at": row["expires_at"],
                        "required_headers": {
                            "Content-Type": "application/octet-stream",
                            "X-Upload-Token": token,
                        },
                    }
                }
            ),
        )

    def _ticket(self, generation: dict[str, Any]) -> dict[str, Any]:
        import json

        with self.engine.connect() as connection:
            row = one(
                connection,
                "SELECT * FROM v2_admission_tickets WHERE ticket_id=:id",
                id=generation["ticket_id"],
            )
        if row is None:
            raise V2Error("integrity_failure", "Upload admission ticket missing")
        return {
            "ticket_id": str(row["ticket_id"]),
            "charge_id": str(generation["charge_id"]),
            "owner": str(row["owner"]),
            "identity": json.loads(row["native_identity"]),
            "root": str(self.root),
        }

    def _drained_source(self, generation: dict[str, Any], retained: int) -> None:
        """Only a proved drained generation may release its unwritten reservation."""
        admission.inventory_owned(
            self.engine, self._ticket(generation), generation["relative_path"]
        )
        with transaction(self.engine) as connection:
            lock(connection, "v2-space:" + str(self.root))
            execute(
                connection,
                "UPDATE v2_storage_reservations SET retained_bytes=:bytes,"
                "reserved_bytes=0,state=:state,updated_at=clock_timestamp() "
                "WHERE reservation_id=:id",
                id=generation["reservation_id"],
                bytes=retained,
                state="retained" if retained else "released",
            )

    def claim(self, identity: str, length: str, token: str) -> dict[str, Any]:
        if not length.isascii() or not length.isdecimal() or len(length) > 12:
            raise V2Error("invalid_request", "Exact Content-Length required")
        owner = uuid4()
        with transaction(self.engine) as connection:
            admission.require(connection, self.root)
            row = self._current(connection, identity, locked=True)
            generation = one(
                connection,
                "SELECT *,expires_at>clock_timestamp() AS valid "
                "FROM v2_upload_generations WHERE generation_id=:id FOR UPDATE",
                id=row["generation_id"],
            )
            assert generation is not None
            if (
                row["state"] != "awaiting_upload"
                or generation["state"] != "issued"
                or not generation["valid"]
                or int(length) != row["declared_bytes"]
                or len(token) > 128
                or not hmac.compare_digest(
                    generation["token_sha256"], hashlib.sha256(token.encode()).hexdigest()
                )
            ):
                raise V2Error("revision_conflict", "Upload generation unavailable")
            ticket = self._ticket(generation)
            if not native_identity.same(ticket["identity"]):
                raise V2Error("revision_conflict", "Upload owner restarted; renew generation")
            execute(
                connection,
                "UPDATE v2_upload_generations SET state='claimed',owner=:owner,"
                "lease_until=clock_timestamp()+interval '60 seconds',updated_at=clock_timestamp() "
                "WHERE generation_id=:id",
                id=generation["generation_id"],
                owner=owner,
            )
            execute(
                connection,
                "UPDATE v2_canonical_imports SET state='uploading',revision=revision+1,"
                "staging_owner=:owner,staging_lease_until=clock_timestamp()+interval '60 seconds',"
                "updated_at=clock_timestamp() WHERE import_id=:id",
                id=row["import_id"],
                owner=owner,
            )
            admission.changed(connection, ticket)
        return dict(generation, owner=owner, ticket=ticket)

    def _account(self, generation: dict[str, Any], received: int) -> None:
        with transaction(self.engine) as connection:
            lock(connection, "v2-space:" + str(self.root))
            row = self._current(connection, str(generation["import_id"]))
            if row["state"] != "uploading" or row["staging_owner"] != generation["owner"]:
                raise V2Error("ownership_lost", "Upload ownership lost")
            live = execute(
                connection,
                "SELECT lease_until>clock_timestamp() FROM v2_upload_generations "
                "WHERE generation_id=:id AND owner=:owner AND state='claimed'",
                id=generation["generation_id"],
                owner=generation["owner"],
            ).scalar_one_or_none()
            if not live:
                raise V2Error("ownership_lost", "Upload lease lost")
            execute(
                connection,
                "UPDATE v2_storage_reservations SET retained_bytes=:bytes,"
                "reserved_bytes=ceiling_bytes-:bytes,updated_at=clock_timestamp() "
                "WHERE reservation_id=:id",
                id=generation["reservation_id"],
                bytes=received,
            )
        with transaction(self.engine) as connection:
            row = self._current(connection, str(generation["import_id"]), locked=True)
            if row["state"] != "uploading" or row["staging_owner"] != generation["owner"]:
                raise V2Error("ownership_lost", "Upload ownership lost")
            execute(
                connection,
                "UPDATE v2_upload_generations SET received_bytes=:bytes WHERE generation_id=:id",
                id=generation["generation_id"],
                bytes=received,
            )
            execute(
                connection,
                "UPDATE v2_canonical_imports SET received_bytes=:bytes WHERE import_id=:id",
                id=generation["import_id"],
                bytes=received,
            )

    def _heartbeat(
        self, generation: dict[str, Any], done: threading.Event, lost: threading.Event
    ) -> None:
        while not done.wait(10):
            try:
                with transaction(self.engine) as connection:
                    renewed = execute(
                        connection,
                        "UPDATE v2_canonical_imports SET staging_lease_until="
                        "clock_timestamp()+interval '60 seconds' WHERE import_id=:id "
                        "AND state='uploading' AND staging_owner=:owner "
                        "AND staging_lease_until>clock_timestamp() RETURNING import_id",
                        id=generation["import_id"],
                        owner=generation["owner"],
                    ).first()
                    if renewed is None:
                        lost.set()
                        return
                    execute(
                        connection,
                        "UPDATE v2_upload_generations SET lease_until=clock_timestamp()+interval "
                        "'60 seconds' WHERE generation_id=:id AND owner=:owner AND state='claimed'",
                        id=generation["generation_id"],
                        owner=generation["owner"],
                    )
            except Exception:
                lost.set()
                return

    async def receive(self, identity: str, request: Request) -> dict[str, Any]:
        from marketlab.storage import store as storage
        from marketlab.storage.backend import StreamWriter

        headers = request.headers
        if (
            len(headers.getlist("content-length")) != 1
            or headers.get("transfer-encoding")
            or headers.get("content-type", "").split(";", 1)[0] != "application/octet-stream"
        ):
            raise V2Error("invalid_request", "Unambiguous raw upload length and media required")
        generation = await _io(
            self.claim, identity, headers["content-length"], headers.get("x-upload-token", "")
        )
        done, lost = threading.Event(), threading.Event()
        worker = threading.Thread(
            target=self._heartbeat, args=(generation, done, lost), daemon=True
        )
        with self._streams_lock:
            self._streams[identity] = lost
        worker.start()
        target = safe_path(self.root, generation["relative_path"])
        stream, received, success = None, 0, False
        writer: StreamWriter | None = None
        group: storage.WriteGroup | None = None
        hasher = hashlib.sha256()
        try:
            group = await _io(
                storage.begin,
                self.engine,
                self.root,
                generation["ticket"],
                str(generation["import_id"]),
                generation["ordinal"],
                [
                    (
                        target.name,
                        storage.media_schema(target),
                        generation["declared_bytes"],
                        generation["source_sha256"],
                    )
                ],
            )
            if group is None:
                await _io(target.parent.mkdir, parents=True, exist_ok=False)
                stream = await _io(target.open, "xb")
            else:
                writer = await _io(group.begin_stream, lost.is_set)
            incoming = request.stream().__aiter__()
            while True:
                try:
                    part = await asyncio.wait_for(anext(incoming), timeout=30)
                except StopAsyncIteration:
                    break
                if lost.is_set():
                    raise V2Error("ownership_lost", "Upload ownership lost")
                if received + len(part) > generation["declared_bytes"]:
                    raise V2Error("integrity_failure", "Upload exceeds declared length")
                for offset in range(0, len(part), 1024 * 1024):
                    chunk = part[offset : offset + 1024 * 1024]
                    # Until the write completes, the full unwritten reservation
                    # remains outstanding. A crash can overcharge, never undercharge.
                    if writer is not None:
                        await _io(writer.write, chunk)
                    else:
                        assert stream is not None
                        await _io(stream.write, chunk)
                    received += len(chunk)
                    await _io(self._account, generation, received)
                    hasher.update(chunk)
            if stream is not None:
                await _io(stream.flush)
                await _io(os.fsync, stream.fileno())
                await _io(stream.close)
                stream = None
            if (
                received != generation["declared_bytes"]
                or hasher.hexdigest() != generation["source_sha256"]
            ):
                raise V2Error("integrity_failure", "Upload length or hash mismatch")
            if group is not None and writer is not None:
                group = await _io(group.complete_stream, writer)
            await _io(self._uploaded, generation, group)
            success = True
        finally:
            if stream is not None:
                await _io(stream.close)
            if writer is not None:
                await _io(writer.close)
            done.set()
            await _io(worker.join, 15)
            with self._streams_lock:
                self._streams.pop(identity, None)
            if worker.is_alive():
                lost.set()  # Retain ticket until exact thread drain is verified.
            elif group is not None:
                if not success:
                    await _io(self._failed, generation, received)
                else:
                    await _io(self._drained_source, generation, received)
                await _io(admission.finish, self.engine, generation["ticket"])
            else:
                # Python's counter may lag a partial successful native write.
                # Reconcile only the fully drained owned file's actual size.
                try:
                    retained = target.stat().st_size if target.exists() else 0
                    if not 0 <= retained <= generation["declared_bytes"]:
                        retained = generation["declared_bytes"]
                except OSError:
                    retained = generation["declared_bytes"]
                if not success:
                    await _io(self._failed, generation, retained)
                await _io(self._drained_source, generation, retained)
                await _io(
                    admission.finish,
                    self.engine,
                    generation["ticket"],
                    retained,
                    generation["relative_path"],
                )
        return await asyncio.to_thread(self.inspect, identity)

    def _uploaded(self, generation: dict[str, Any], group: Any = None) -> None:
        from marketlab.storage import store as storage

        with transaction(self.engine) as connection:
            row = self._current(connection, str(generation["import_id"]), locked=True)
            if (
                row["state"] != "uploading"
                or row["staging_owner"] != generation["owner"]
                or row["generation_id"] != generation["generation_id"]
            ):
                raise V2Error("ownership_lost", "Upload ownership lost")
            live = execute(
                connection,
                "SELECT staging_lease_until>clock_timestamp() "
                "FROM v2_canonical_imports WHERE import_id=:id",
                id=row["import_id"],
            ).scalar_one()
            if not live:
                raise V2Error("ownership_lost", "Upload lease expired")
            if group is not None:
                storage.register(
                    connection, group, "upload_generation", str(generation["generation_id"])
                )
            execute(
                connection,
                "UPDATE v2_upload_generations SET state='uploaded',owner=NULL,lease_until=NULL,"
                "updated_at=clock_timestamp() WHERE generation_id=:id",
                id=generation["generation_id"],
            )
            execute(
                connection,
                "UPDATE v2_canonical_imports SET state='uploaded',revision=revision+1,"
                "staging_owner=NULL,staging_lease_until=NULL,updated_at=clock_timestamp() "
                "WHERE import_id=:id",
                id=row["import_id"],
            )

    def _failed(self, generation: dict[str, Any], received: int) -> None:
        with transaction(self.engine) as connection:
            row = self._current(connection, str(generation["import_id"]), locked=True)
            if row["state"] == "uploading" and row["staging_owner"] == generation["owner"]:
                execute(
                    connection,
                    "UPDATE v2_canonical_imports SET state='upload_failed',revision=revision+1,"
                    "error_code='upload_failed',staging_owner=NULL,staging_lease_until=NULL,"
                    "updated_at=clock_timestamp() WHERE import_id=:id",
                    id=row["import_id"],
                )
            execute(
                connection,
                "UPDATE v2_upload_generations SET state=CASE WHEN state='cancelled' "
                "THEN state ELSE 'failed' END,owner=NULL,lease_until=NULL,received_bytes=:bytes,"
                "updated_at=clock_timestamp() WHERE generation_id=:id AND state='claimed'",
                id=generation["generation_id"],
                bytes=received,
            )

    def renew(self, identity: str, body: dict[str, Any], key: str) -> dict[str, Any]:
        revision = _revision(body)
        request = dict(body, id=identity)
        self.recover(identity)
        with transaction(self.engine) as connection:
            old = operation(connection, "browser-renew", key, request)
            if old is not None:
                return old
            current = self._current(connection, identity)
            expired = one(
                connection,
                "SELECT *,expires_at<=clock_timestamp() AS expired "
                "FROM v2_upload_generations WHERE generation_id=:id FOR UPDATE",
                id=current["generation_id"],
            )
            if (
                expired is not None
                and expired["state"] == "issued"
                and expired["expired"]
                and current["state"] == "awaiting_upload"
                and current["revision"] == revision
            ):
                if safe_path(self.root, expired["relative_path"]).exists():
                    raise V2Error(
                        "integrity_failure", "Unclaimed generation contains unexplained bytes"
                    )
                execute(
                    connection,
                    "UPDATE v2_upload_generations SET state='retired' WHERE generation_id=:id",
                    id=expired["generation_id"],
                )
            else:
                expired = None
        if expired is not None:
            previous = self._ticket(expired)
            if native_identity.same(previous["identity"]):
                self._drained_source(expired, 0)
                admission.finish(self.engine, previous, 0, expired["relative_path"])
        ticket = admission.acquire(
            self.engine,
            self.root,
            "upload",
            current["declared_bytes"],
            identity,
            physical_bytes=current["declared_bytes"],
        )
        if ticket is None:
            raise V2Error("unavailable", "Storage initialization required")
        try:
            with transaction(self.engine) as connection:
                old = operation(connection, "browser-renew", key, request)
                if old is not None:
                    result = old
                    used = False
                else:
                    row = self._current(connection, identity, locked=True)
                    prior = one(
                        connection,
                        "SELECT *,expires_at<=clock_timestamp() AS expired FROM "
                        "v2_upload_generations WHERE generation_id=:id",
                        id=row["generation_id"],
                    )
                    assert prior is not None
                    if (
                        row["revision"] != revision
                        or row["state"] not in {"awaiting_upload", "upload_failed"}
                        or (row["state"] == "awaiting_upload" and not prior["expired"])
                    ):
                        raise V2Error("revision_conflict", "Import cannot renew")
                    generation = uuid4()
                    relative = f"staging-v2/{identity}/{generation}/source.{row['format']}"
                    result = self._generation(
                        connection,
                        identity,
                        generation,
                        relative,
                        row["declared_bytes"],
                        row["source_sha256"],
                        prior["ordinal"] + 1,
                        ticket,
                    )
                    execute(
                        connection,
                        "UPDATE v2_upload_generations SET state='retired' WHERE generation_id=:id",
                        id=prior["generation_id"],
                    )
                    execute(
                        connection,
                        "UPDATE v2_canonical_imports SET generation_id=:generation,"
                        "source_relative_path=:path,state='awaiting_upload',revision=revision+1,"
                        "received_bytes=0,error_code=NULL,updated_at=clock_timestamp() "
                        "WHERE import_id=:id",
                        id=identity,
                        generation=generation,
                        path=relative,
                    )
                    admission.activate(connection, ticket, identity, generation=generation)
                    result.update(id=identity, state="awaiting_upload", revision=revision + 1)
                    result = save_operation(connection, "browser-renew", key, request, result)
                    used = True
            if not used:
                admission.finish(self.engine, ticket, 0)
            return result
        except BaseException:
            admission.finish(self.engine, ticket, 0)
            raise

    def finalize(self, identity: str, body: dict[str, Any], key: str) -> dict[str, Any]:
        from marketlab.storage import store as storage
        from marketlab.storage.materialize import materialize_package, without_cache

        revision = _revision(body, True)
        request = dict(body, id=identity)
        with transaction(self.engine) as connection:
            old = operation(connection, "browser-finalize", key, request)
            if old is not None:
                return old
            row = self._current(connection, identity)
            binding = (
                storage.snapshot(connection, "upload_generation", str(row["generation_id"]))
                if row["state"] == "uploaded" and storage.enabled(connection)
                else None
            )
        if row["state"] != "uploaded" or str(row["generation_id"]) != body["generation"]:
            raise V2Error("revision_conflict", "Verified current upload required")
        path = safe_path(self.root, row["source_relative_path"])
        refs = binding.refs if binding is not None else None
        with (
            without_cache(),
            materialize_package(self.engine, self.root, refs, lambda: path.parent) as directory,
        ):
            resolved = directory / path.name
            stat = _signature(resolved)
            if stat[2] != row["declared_bytes"] or sha256_file(resolved) != row["source_sha256"]:
                raise V2Error("integrity_failure", "Uploaded source changed")
        with transaction(self.engine) as connection:
            old = operation(connection, "browser-finalize", key, request)
            if old is not None:
                return old
            current = self._current(connection, identity, locked=True)
            if (
                current["revision"] != revision
                or current["state"] != "uploaded"
                or current["generation_id"] != row["generation_id"]
                or (refs is None and _signature(path) != stat)
                or (
                    binding is not None
                    and storage.snapshot(
                        connection, "upload_generation", str(current["generation_id"])
                    )
                    != binding
                )
            ):
                raise V2Error("revision_conflict", "Import changed before finalization")
            day = current["trade_date"]
            submission, children = jobs.create_submission(
                connection,
                {"manifest": current["metadata_json"], "content_length": current["declared_bytes"]},
                [current["instrument_id"]],
                day,
                day + timedelta(days=1),
                import_id=uid(identity),
            )
            execute(
                connection,
                "UPDATE v2_canonical_imports SET state='queued',revision=revision+1,"
                "submission_id=:submission,updated_at=clock_timestamp() WHERE import_id=:id",
                id=identity,
                submission=submission,
            )
            return save_operation(
                connection,
                "browser-finalize",
                key,
                request,
                {
                    "id": identity,
                    "state": "queued",
                    "revision": revision + 1,
                    "submission_id": str(submission),
                    "job_id": str(children[0]),
                },
            )

    def cancel(self, identity: str, body: dict[str, Any], key: str) -> dict[str, Any]:
        revision = _revision(body)
        request = dict(body, id=identity)
        with transaction(self.engine) as connection:
            old = operation(connection, "browser-cancel", key, request)
            if old is not None:
                return old
            row = self._current(connection, identity, locked=True)
            if row["revision"] != revision or row["state"] in {"succeeded", "failed"}:
                raise V2Error("revision_conflict", "Import cannot cancel at this revision")
            if row["submission_id"] is not None:
                job = one(
                    connection,
                    "SELECT * FROM v2_ingestion_jobs WHERE import_id=:id FOR UPDATE",
                    id=identity,
                )
                assert job is not None
                # Existing durable cancellation linearization, under the same row locks.
                if job["state"] in {"succeeded", "failed"}:
                    raise V2Error("revision_conflict", "Completed import cannot cancel")
                if job["state"] in {"queued", "retry_wait"}:
                    jobs.finish(connection, job, "cancelled", "cancelled", "cancelled")
                elif job["state"] == "running":
                    execute(
                        connection,
                        "UPDATE v2_ingestion_jobs SET cancel_requested=true,revision=revision+1 "
                        "WHERE job_id=:id",
                        id=job["job_id"],
                    )
                    execute(
                        connection,
                        "UPDATE v2_canonical_imports SET revision=revision+1 WHERE import_id=:id",
                        id=identity,
                    )
            elif row["state"] != "cancelled":
                execute(
                    connection,
                    "UPDATE v2_canonical_imports SET state='cancelled',revision=revision+1,"
                    "staging_owner=NULL,staging_lease_until=NULL,updated_at=clock_timestamp() "
                    "WHERE import_id=:id",
                    id=identity,
                )
                execute(
                    connection,
                    "UPDATE v2_upload_generations SET state='cancelled',owner=NULL,"
                    "lease_until=NULL "
                    "WHERE generation_id=:id",
                    id=row["generation_id"],
                )
            result = save_operation(
                connection,
                "browser-cancel",
                key,
                request,
                {
                    "id": identity,
                    "state": "cancellation_requested" if row["state"] == "running" else "cancelled",
                },
            )
        with self._streams_lock:
            stream = self._streams.get(identity)
            if stream is not None:
                stream.set()
        # The active receiver owns drain/release. An unclaimed or verified upload has no writer.
        # upload_failed may be a lease-expiry projection while the old native
        # writer is still alive. Only its receiver drain or native death proves
        # that generation safe to reconcile; process identity/state alone do not.
        if stream is None and row["state"] in {"awaiting_upload", "uploaded"}:
            with self.engine.connect() as connection:
                generation = one(
                    connection,
                    "SELECT * FROM v2_upload_generations WHERE generation_id=:id",
                    id=row["generation_id"],
                )
            if generation is not None:
                ticket = self._ticket(generation)
                if native_identity.same(ticket["identity"]):
                    self._drained_source(generation, generation["received_bytes"])
                    admission.finish(
                        self.engine,
                        ticket,
                        generation["received_bytes"],
                        generation["relative_path"],
                    )
        return result

    def recover(self, identity: str) -> None:
        with transaction(self.engine) as connection:
            row = self._current(connection, identity, locked=True)
            if row["state"] != "uploading":
                return
            live = execute(
                connection,
                "SELECT staging_lease_until>clock_timestamp() FROM "
                "v2_canonical_imports WHERE import_id=:id",
                id=identity,
            ).scalar_one()
            if live:
                return
            execute(
                connection,
                "UPDATE v2_canonical_imports SET state='upload_failed',revision=revision+1,"
                "staging_owner=NULL,staging_lease_until=NULL,error_code='upload_expired',"
                "updated_at=clock_timestamp() WHERE import_id=:id",
                id=identity,
            )
            execute(
                connection,
                "UPDATE v2_upload_generations SET state='failed',owner=NULL,lease_until=NULL "
                "WHERE generation_id=:id AND state='claimed'",
                id=row["generation_id"],
            )
