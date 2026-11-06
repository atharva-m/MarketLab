"""Bounded immutable local and versioned object storage operations."""

import hashlib
import os
import re
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, BinaryIO, Protocol, cast
from urllib.parse import urlsplit
from uuid import uuid4

from marketlab.config import Settings
from marketlab.datasets.v2.common import V2Error, digest, safe_path

CHUNK = 1024**2
PART = 16 * CHUNK
MAX_OBJECT = 4 * 1024**3
MAX_PARTS = MAX_OBJECT // PART
OBJECT_DEADLINE = 1800.0
_SEGMENT = re.compile(r"[A-Za-z0-9_.=-]+")
_ALIAS = re.compile(r"[A-Za-z0-9_-]{1,64}")
_HASH = re.compile(r"[0-9a-f]{64}")


def object_key(key: str) -> str:
    if (
        not key
        or len(key) > 1024
        or any(part in {".", ".."} or _SEGMENT.fullmatch(part) is None for part in key.split("/"))
    ):
        raise V2Error("integrity_failure", "Invalid artifact location")
    return key


@dataclass(frozen=True)
class ObjectRef:
    alias: str
    key: str
    version: str | None
    length: int
    sha256: str
    member: str
    media_schema: str

    def __post_init__(self) -> None:
        object_key(self.key)
        if (
            not _ALIAS.fullmatch(self.alias)
            or not 1 <= self.length <= MAX_OBJECT
            or not _HASH.fullmatch(self.sha256)
            or len(self.member) > 128
            or self.member in {".", ".."}
            or not re.fullmatch(r"[A-Za-z0-9_.-]+", self.member)
            or not re.fullmatch(r"[A-Za-z0-9_.+/-]{1,128}", self.media_schema)
            or (self.alias == "local" and self.version is not None)
            or (self.version is not None and not _valid_version(self.version))
        ):
            raise V2Error("integrity_failure", "Invalid artifact reference")


def _valid_version(value: object) -> bool:
    return isinstance(value, str) and 0 < len(value) <= 1024 and value != "null"


def check(cancelled: Callable[[], bool] | None, deadline: float) -> None:
    if cancelled is not None and cancelled():
        raise V2Error("ownership_lost", "Storage operation cancelled")
    if time.monotonic() >= deadline:
        raise V2Error("unavailable", "Storage operation deadline exceeded")


class Input(Protocol):
    def read(self, n: int, /) -> bytes: ...


class StorageUnavailable(V2Error):
    transient = True

    def __init__(self) -> None:
        super().__init__("unavailable", "Object storage temporarily unavailable")


def copy_verified(
    source: Input,
    target: BinaryIO | None,
    ref: ObjectRef,
    *,
    cancelled: Callable[[], bool] | None = None,
    deadline: float | None = None,
) -> None:
    deadline = time.monotonic() + OBJECT_DEADLINE if deadline is None else deadline
    sha, remaining = hashlib.sha256(), ref.length
    while remaining:
        check(cancelled, deadline)
        block = source.read(min(CHUNK, remaining))
        if not block or len(block) > remaining:
            raise V2Error("integrity_failure", "Artifact length mismatch")
        remaining -= len(block)
        sha.update(block)
        if target is not None and target.write(block) != len(block):
            raise V2Error("unavailable", "Artifact materialization incomplete")
    check(cancelled, deadline)
    if source.read(1) or sha.hexdigest() != ref.sha256:
        raise V2Error("integrity_failure", "Artifact content mismatch")


class Backend(Protocol):
    alias: str

    def stat(self, ref: ObjectRef) -> None: ...

    def read_verified(
        self, ref: ObjectRef, target: BinaryIO, *, cancelled: Callable[[], bool] | None = None
    ) -> None: ...

    def put_new(
        self,
        ref: ObjectRef,
        source: Input,
        *,
        multipart: Callable[[str], None],
        cancelled: Callable[[], bool] | None = None,
    ) -> ObjectRef: ...

    def delete_unreferenced(self, ref: ObjectRef) -> None: ...


class StreamWriter(Protocol):
    def write(self, data: bytes) -> None: ...
    def complete(self) -> ObjectRef: ...
    def close(self) -> None: ...


class LocalWriter:
    def __init__(
        self, backend: "LocalBackend", ref: ObjectRef, cancelled: Callable[[], bool]
    ) -> None:
        self.backend, self.ref, self.cancelled = backend, ref, cancelled
        self.target = backend._path(ref)
        self.pending = self.target.with_name(f".{self.target.name}.partial")
        self.target.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.pending.open("xb")
        self.digest = hashlib.sha256()
        self.received = 0
        self.deadline = time.monotonic() + OBJECT_DEADLINE

    def write(self, data: bytes) -> None:
        check(self.cancelled, self.deadline)
        if self.received + len(data) > self.ref.length or self.file.write(data) != len(data):
            raise V2Error("integrity_failure", "Local artifact upload length mismatch")
        self.digest.update(data)
        self.received += len(data)

    def complete(self) -> ObjectRef:
        check(self.cancelled, self.deadline)
        if self.received != self.ref.length or self.digest.hexdigest() != self.ref.sha256:
            raise V2Error("integrity_failure", "Local artifact upload content mismatch")
        self.file.flush()
        os.fsync(self.file.fileno())
        self.close()
        _publish_local(self.pending, self.target)
        self.backend._read(self.ref, None, self.cancelled)
        return self.ref

    def close(self) -> None:
        self.file.close()


def _publish_local(pending: Path, target: Path) -> None:
    if os.name == "nt":
        os.rename(pending, target)  # Windows rename rejects an existing target.
    else:
        os.link(pending, target)
        pending.unlink()


class LocalBackend:
    alias = "local"

    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, ref: ObjectRef) -> Path:
        if ref.alias != self.alias or ref.version is not None:
            raise V2Error("integrity_failure", "Artifact backend mismatch")
        root = self.root.absolute()
        if any(part.is_symlink() or part.is_junction() for part in (root, *root.parents)):
            raise V2Error("integrity_failure", "Unsafe local storage root")
        path = safe_path(root, ref.key)
        lexical = root
        for segment in ref.key.split("/"):
            lexical = lexical / segment
            if lexical.is_symlink() or lexical.is_junction():
                raise V2Error("integrity_failure", "Unsafe local artifact location")
        if os.name == "nt":
            text = str(path)
            if not text.startswith("\\\\?\\"):
                path = Path(
                    "\\\\?\\UNC\\" + text[2:] if text.startswith("\\\\") else "\\\\?\\" + text
                )
        return path

    def _read(
        self, ref: ObjectRef, target: BinaryIO | None, cancelled: Callable[[], bool] | None
    ) -> None:
        path = self._path(ref)
        try:
            if not path.is_file() or path.stat().st_size != ref.length:
                raise V2Error("integrity_failure", "Registered local artifact missing or changed")
            with path.open("rb") as source:
                copy_verified(source, target, ref, cancelled=cancelled)
        except FileNotFoundError:
            raise V2Error("integrity_failure", "Registered local artifact missing") from None
        except OSError:
            raise V2Error("unavailable", "Local artifact read failed") from None

    def stat(self, ref: ObjectRef) -> None:
        self._read(ref, None, None)

    def read_verified(
        self, ref: ObjectRef, target: BinaryIO, *, cancelled: Callable[[], bool] | None = None
    ) -> None:
        self._read(ref, target, cancelled)

    def put_new(
        self,
        ref: ObjectRef,
        source: Input,
        *,
        multipart: Callable[[str], None],
        cancelled: Callable[[], bool] | None = None,
    ) -> ObjectRef:
        target = self._path(ref)
        pending = target.with_name(f".{target.name}.partial")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with pending.open("xb") as file:
                copy_verified(source, file, ref, cancelled=cancelled)
                file.flush()
                os.fsync(file.fileno())
            _publish_local(pending, target)
        except FileExistsError:
            raise V2Error("integrity_failure", "Immutable artifact already exists") from None
        except OSError:
            raise V2Error("unavailable", "Local artifact write failed") from None
        self._read(ref, None, cancelled)
        return ref

    def delete_unreferenced(self, ref: ObjectRef) -> None:
        path = self._path(ref)
        self.stat(ref)
        try:
            path.unlink()
        except OSError:
            raise V2Error("unavailable", "Local artifact removal failed") from None
        if path.exists():
            raise V2Error("integrity_failure", "Local artifact absence unverified")


@dataclass(frozen=True)
class ObjectConfig:
    alias: str
    endpoint: str
    region: str
    bucket: str
    prefix: str

    @property
    def fingerprint(self) -> str:
        return digest([self.endpoint, self.region, self.bucket, self.prefix])

    @classmethod
    def from_settings(cls, settings: Settings) -> "ObjectConfig | None":
        alias = settings.storage_s3_alias
        if settings.storage_s3_endpoint is None and settings.storage_backend == "local":
            return None
        endpoint = settings.storage_s3_endpoint or ""
        bucket = settings.storage_s3_bucket or ""
        region = settings.storage_s3_region
        try:
            parsed = urlsplit(endpoint)
            hostname = parsed.hostname
            _ = parsed.port
        except ValueError:
            raise V2Error("storage_denied", "Invalid object storage configuration") from None
        if (
            not _ALIAS.fullmatch(alias)
            or alias == "local"
            or settings.storage_backend not in {"local", alias}
            or parsed.scheme not in {"https", "http"}
            or not hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or (parsed.scheme == "http" and hostname not in {"localhost", "127.0.0.1", "::1"})
            or not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", bucket)
            or not re.fullmatch(r"[A-Za-z0-9-]{1,64}", region)
        ):
            raise V2Error("storage_denied", "Invalid object storage configuration")
        prefix = object_key(settings.storage_s3_prefix)
        if len(prefix) > 240:
            raise V2Error("storage_denied", "Invalid object storage configuration")
        return cls(alias, f"{parsed.scheme}://{parsed.netloc.lower()}", region, bucket, prefix)


class S3Backend:
    def __init__(self, config: ObjectConfig, client: Any, *, owns_client: bool = False) -> None:
        self.config = config
        self.alias = config.alias
        self._client = client
        self._owns_client = owns_client
        self._closed = False

    def close(self) -> None:
        if self._owns_client and not self._closed:
            self._closed = True
            self._client.close()

    @classmethod
    def configured(cls, config: ObjectConfig, settings: Settings) -> "S3Backend":
        from botocore.config import Config  # type: ignore[import-untyped]
        from botocore.session import Session  # type: ignore[import-untyped]

        key, secret, token = (
            settings.storage_s3_access_key,
            settings.storage_s3_secret_key,
            settings.storage_s3_session_token,
        )
        if (
            key is None
            or secret is None
            or not key.get_secret_value()
            or not secret.get_secret_value()
        ):
            raise V2Error("storage_denied", "Object storage credentials required")
        try:
            client = Session().create_client(
                "s3",
                endpoint_url=config.endpoint,
                region_name=config.region,
                aws_access_key_id=key.get_secret_value(),
                aws_secret_access_key=secret.get_secret_value(),
                aws_session_token=token.get_secret_value() if token else None,
                config=Config(
                    signature_version="s3v4",
                    connect_timeout=5,
                    read_timeout=30,
                    retries={"total_max_attempts": 1},
                    s3={"addressing_style": "path"},
                    proxies={},
                ),
            )
            client.meta.events.register_first("needs-retry.s3", _reject_redirect)
        except Exception:
            raise V2Error("storage_denied", "Object storage client initialization failed") from None
        return cls(config, client, owns_client=True)

    def _run(self, method: str, **params: Any) -> Mapping[str, Any]:
        if self._closed:
            raise V2Error("storage_denied", "Object storage client is closed")
        try:
            return cast(
                Mapping[str, Any],
                getattr(self._client, method)(Bucket=self.config.bucket, **params),
            )
        except V2Error:
            raise
        except Exception as error:
            raise _storage_error(error) from None

    def _key(self, ref: ObjectRef) -> str:
        if ref.alias != self.alias:
            raise V2Error("integrity_failure", "Artifact backend mismatch")
        return object_key(f"{self.config.prefix}/{ref.key}")

    def _pinned(self, ref: ObjectRef) -> dict[str, str]:
        if not ref.version:
            raise V2Error("integrity_failure", "Artifact generation is missing")
        return {"Key": self._key(ref), "VersionId": ref.version}

    @staticmethod
    def _verify_headers(ref: ObjectRef, result: Mapping[str, Any]) -> None:
        if result.get("VersionId") != ref.version or result.get("ContentLength") != ref.length:
            raise V2Error("integrity_failure", "Registered object generation changed")

    def require_versioning(self) -> None:
        if self._run("get_bucket_versioning").get("Status") != "Enabled":
            raise V2Error("storage_denied", "Object storage versioning is required")

    def stat(self, ref: ObjectRef) -> None:
        self._verify_headers(ref, self._get_registered("head_object", ref))

    def _get_registered(self, method: str, ref: ObjectRef) -> Mapping[str, Any]:
        try:
            return self._run(method, **self._pinned(ref))
        except V2Error as error:
            if error.code == "storage_missing":
                raise V2Error("integrity_failure", "Registered object generation missing") from None
            raise

    def _read(
        self,
        ref: ObjectRef,
        target: BinaryIO | None,
        cancelled: Callable[[], bool] | None,
        deadline: float,
    ) -> None:
        check(cancelled, deadline)
        result = self._get_registered("get_object", ref)
        body = result.get("Body")
        if body is None:
            raise V2Error("integrity_failure", "Object storage response is incomplete")
        try:
            self._verify_headers(ref, result)
            copy_verified(body, target, ref, cancelled=cancelled, deadline=deadline)
        except V2Error:
            raise
        except Exception as error:
            raise _storage_error(error) from None
        finally:
            body.close()

    def read_verified(
        self, ref: ObjectRef, target: BinaryIO, *, cancelled: Callable[[], bool] | None = None
    ) -> None:
        self._read(ref, target, cancelled, time.monotonic() + OBJECT_DEADLINE)

    def begin_multipart(
        self,
        ref: ObjectRef,
        persist: Callable[[str], None],
        cancelled: Callable[[], bool] | None = None,
    ) -> "MultipartWriter":
        return MultipartWriter(self, ref, persist, cancelled)

    def put_new(
        self,
        ref: ObjectRef,
        source: Input,
        *,
        multipart: Callable[[str], None],
        cancelled: Callable[[], bool] | None = None,
    ) -> ObjectRef:
        if ref.version is not None:
            raise V2Error("integrity_failure", "Cannot overwrite an object generation")
        deadline = time.monotonic() + OBJECT_DEADLINE
        if ref.length <= PART:
            check(cancelled, deadline)
            data = source.read(ref.length)
            if (
                len(data) != ref.length
                or source.read(1)
                or hashlib.sha256(data).hexdigest() != ref.sha256
            ):
                raise V2Error("integrity_failure", "Artifact content mismatch")
            result = self._run(
                "put_object",
                Key=self._key(ref),
                Body=data,
                ContentLength=ref.length,
                ContentType=ref.media_schema,
                IfNoneMatch="*",
            )
            return self._verified_result(ref, result, cancelled, deadline)
        writer = self.begin_multipart(ref, multipart, cancelled)
        while block := source.read(CHUNK):
            writer.write(block)
        return writer.complete()

    def _verified_result(
        self,
        ref: ObjectRef,
        result: Mapping[str, Any],
        cancelled: Callable[[], bool] | None,
        deadline: float,
    ) -> ObjectRef:
        version = result.get("VersionId")
        if not _valid_version(version):
            raise V2Error("integrity_failure", "Object storage generation is unpinned")
        pinned = replace(ref, version=version)
        self._read(pinned, None, cancelled, deadline)
        return pinned

    def delete_unreferenced(self, ref: ObjectRef) -> None:
        pinned = self._pinned(ref)
        self.stat(ref)
        self._run("delete_object", **pinned)
        try:
            self._run("head_object", **pinned)
        except V2Error as error:
            if error.code == "storage_missing":
                return
            raise
        raise V2Error("integrity_failure", "Object generation absence unverified")


class MultipartWriter:
    def __init__(
        self,
        backend: S3Backend,
        ref: ObjectRef,
        persist: Callable[[str], None],
        cancelled: Callable[[], bool] | None,
    ) -> None:
        if ref.version is not None:
            raise V2Error("integrity_failure", "Cannot overwrite an object generation")
        self.backend, self.ref, self.cancelled = backend, ref, cancelled
        self.deadline = time.monotonic() + OBJECT_DEADLINE
        self.key = backend._key(ref)
        self.buffer = bytearray()
        self.parts: list[dict[str, Any]] = []
        self.digest = hashlib.sha256()
        self.received = 0
        self.completed = False
        check(cancelled, self.deadline)
        result = backend._run("create_multipart_upload", Key=self.key, ContentType=ref.media_schema)
        upload_id = result.get("UploadId")
        if not isinstance(upload_id, str) or not 1 <= len(upload_id) <= 1024:
            raise V2Error("integrity_failure", "Multipart initiation receipt missing")
        persist(upload_id)
        self.upload_id = upload_id

    def _part(self) -> None:
        check(self.cancelled, self.deadline)
        number = len(self.parts) + 1
        if number > MAX_PARTS or not self.buffer:
            raise V2Error("integrity_failure", "Multipart part bound exceeded")
        result = self.backend._run(
            "upload_part",
            Key=self.key,
            UploadId=self.upload_id,
            PartNumber=number,
            Body=bytes(self.buffer),
            ContentLength=len(self.buffer),
        )
        etag = result.get("ETag")
        if not isinstance(etag, str) or not 1 <= len(etag) <= 1024:
            raise V2Error("integrity_failure", "Multipart part receipt missing")
        self.parts.append({"ETag": etag, "PartNumber": number})
        self.buffer.clear()

    def write(self, data: bytes) -> None:
        check(self.cancelled, self.deadline)
        if self.completed or self.received + len(data) > self.ref.length:
            raise V2Error("integrity_failure", "Multipart length exceeded")
        self.received += len(data)
        self.digest.update(data)
        offset = 0
        while offset < len(data):
            step = min(PART - len(self.buffer), len(data) - offset)
            self.buffer.extend(data[offset : offset + step])
            offset += step
            if len(self.buffer) == PART:
                self._part()

    def complete(self) -> ObjectRef:
        check(self.cancelled, self.deadline)
        if (
            self.completed
            or self.received != self.ref.length
            or self.digest.hexdigest() != self.ref.sha256
        ):
            raise V2Error("integrity_failure", "Multipart length or hash mismatch")
        if self.buffer:
            self._part()
        self.completed = True
        result = self.backend._run(
            "complete_multipart_upload",
            Key=self.key,
            UploadId=self.upload_id,
            MultipartUpload={"Parts": self.parts},
            IfNoneMatch="*",
        )
        return self.backend._verified_result(self.ref, result, self.cancelled, self.deadline)

    def close(self) -> None:
        # The durable intent remains charged. Closing never aborts a remote upload.
        self.buffer.clear()
        self.backend.close()


def _reject_redirect(
    response: tuple[Any, Any] | None = None, operation: Any = None, **kwargs: Any
) -> None:
    if response is None:
        return
    status, code = response[0].status_code, response[1].get("Error", {}).get("Code")
    # Botocore's region redirector is independent of the general retry budget.
    if (
        300 <= status < 400
        or code
        in {
            "PermanentRedirect",
            "AuthorizationHeaderMalformed",
            "IllegalLocationConstraintException",
        }
        or (getattr(operation, "name", None) in {"HeadObject", "HeadBucket"} and status == 400)
    ):
        raise V2Error("storage_denied", "Object storage redirects are disabled")


def _storage_error(error: Exception) -> V2Error:
    from botocore.exceptions import (  # type: ignore[import-untyped]
        ClientError,
        ConnectionClosedError,
        ConnectTimeoutError,
        EndpointConnectionError,
        IncompleteReadError,
        ReadTimeoutError,
        ResponseStreamingError,
    )

    if isinstance(error, ClientError):
        status = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        code = error.response.get("Error", {}).get("Code")
        if status == 404 and code in {"404", "NoSuchKey", "NoSuchVersion", "NotFound"}:
            return V2Error("storage_missing", "Registered object generation missing")
        if status in {408, 429} or (isinstance(status, int) and 500 <= status <= 599):
            return StorageUnavailable()
        if status in {409, 412}:
            return V2Error("integrity_failure", "Immutable object write conflict")
    if isinstance(error, IncompleteReadError):
        return V2Error("integrity_failure", "Object storage response is truncated")
    if isinstance(
        error,
        (
            ConnectionClosedError,
            ConnectTimeoutError,
            EndpointConnectionError,
            ReadTimeoutError,
            ResponseStreamingError,
        ),
    ):
        return StorageUnavailable()
    return V2Error("storage_denied", "Object storage request rejected")


def backend_for(root: Path, alias: str, settings: Settings | None = None) -> Backend:
    if alias == "local":
        return LocalBackend(root)
    settings = settings if settings is not None else Settings()
    config = ObjectConfig.from_settings(settings)
    if config is None or alias != config.alias:
        raise V2Error("storage_denied", "Registered object storage binding unavailable")
    return S3Backend.configured(config, settings)


def close_backend(backend: Backend) -> None:
    if isinstance(backend, S3Backend):
        backend.close()


@contextmanager
def managed_backend[BackendType: Backend](backend: BackendType) -> Iterator[BackendType]:
    try:
        yield backend
    finally:
        close_backend(backend)


def new_prefix(owner: str, token: int) -> str:
    from uuid import UUID

    if token < 0:
        raise V2Error("integrity_failure", "Invalid storage fencing token")
    return f"attempts/{UUID(owner)}/{token}/{uuid4()}"
