"""Local immutable publication and whole-package sealing without S3."""

import hashlib
import io
import json
from pathlib import Path

import pytest

from marketlab.datasets.v2.common import V2Error
from marketlab.storage.backend import LocalBackend, LocalWriter, ObjectRef
from marketlab.storage.store import describe


def reference(data: bytes):
    return ObjectRef(
        "local",
        "attempts/job/1/write/results.json",
        None,
        len(data),
        hashlib.sha256(data).hexdigest(),
        "results.json",
        "application/json",
    )


def test_local_publication_is_verified_and_never_overwrites(tmp_path):
    backend, data = LocalBackend(tmp_path), b"exact immutable bytes"
    ref = reference(data)
    assert backend.put_new(ref, io.BytesIO(data), multipart=lambda _: pytest.fail()) == ref
    with pytest.raises(V2Error, match="already exists"):
        backend.put_new(ref, io.BytesIO(data), multipart=lambda _: pytest.fail())
    output = io.BytesIO()
    backend.read_verified(ref, output)
    assert output.getvalue() == data
    (tmp_path / ref.key).write_bytes(b"x" * len(data))
    with pytest.raises(V2Error, match="content mismatch"):
        backend.stat(ref)


def test_local_stream_rejects_wrong_hash_and_retains_partial(tmp_path):
    ref = reference(b"expected")
    writer = LocalWriter(LocalBackend(tmp_path), ref, lambda: False)
    writer.write(b"unexpected"[: ref.length])
    try:
        with pytest.raises(V2Error, match="content mismatch"):
            writer.complete()
    finally:
        writer.close()
    assert not (tmp_path / ref.key).exists()
    assert (tmp_path / ref.key).with_name(".results.json.partial").stat().st_size == ref.length


def test_package_seal_rejects_unregistered_member_changed_after_validation(tmp_path):
    data = b'{"schema":"fixture"}'
    summary, manifest = tmp_path / "spec.json", tmp_path / "manifest.json"
    summary.write_bytes(data)
    manifest.write_text(
        json.dumps(
            {
                "artifacts": {
                    "spec.json": {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                }
            }
        )
    )
    seal = hashlib.sha256(manifest.read_bytes()).hexdigest()
    files = {"manifest.json": manifest, "spec.json": summary}
    assert len(describe(files, seal)) == 2
    summary.write_bytes(b"x" * len(data))
    with pytest.raises(V2Error, match="members changed"):
        describe(files, seal)
    manifest.write_text(
        json.dumps(
            {
                "artifacts": {
                    "spec.json": {
                        "bytes": len(data),
                        "sha256": hashlib.sha256(summary.read_bytes()).hexdigest(),
                    }
                }
            }
        )
    )
    with pytest.raises(V2Error, match="manifest changed"):
        describe(files, seal)


def test_local_symlink_component_fails_closed(tmp_path: Path):
    actual, link = tmp_path / "actual", tmp_path / "linked"
    actual.mkdir()
    try:
        link.symlink_to(actual, target_is_directory=True)
    except OSError:
        pytest.skip("OS does not permit creating this owned symlink fixture")
    data = b"registered"
    ref = ObjectRef(
        "local",
        "linked/results.json",
        None,
        len(data),
        hashlib.sha256(data).hexdigest(),
        "results.json",
        "application/json",
    )
    (actual / "results.json").write_bytes(data)
    with pytest.raises(V2Error, match="Unsafe|unsafe"):
        LocalBackend(tmp_path).stat(ref)
