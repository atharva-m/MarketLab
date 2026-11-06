"""S3 SDK protocol cases. Run only under separately authorized S3 validation."""

import hashlib
import io
from dataclasses import replace
from types import SimpleNamespace

import pytest
from botocore.exceptions import ConnectTimeoutError
from botocore.response import StreamingBody
from botocore.session import Session
from botocore.stub import Stubber

from marketlab.datasets.v2.common import V2Error
from marketlab.storage.backend import (
    ObjectConfig,
    ObjectRef,
    S3Backend,
    StorageUnavailable,
    _reject_redirect,
    managed_backend,
)

pytestmark = pytest.mark.s3
DATA = b"verified artifact bytes"
KEY = "phase6/attempts/job/1/attempt/manifest.json"


@pytest.fixture
def backend():
    client = Session().create_client(
        "s3",
        region_name="us-east-1",
        endpoint_url="https://unused.invalid",
        aws_access_key_id="mock-access",
        aws_secret_access_key="mock-secret",
    )
    config = ObjectConfig("archive", "https://unused.invalid", "us-east-1", "owned", "phase6")
    return S3Backend(config, client), Stubber(client)


def ref():
    return ObjectRef(
        "archive",
        KEY.removeprefix("phase6/"),
        None,
        len(DATA),
        hashlib.sha256(DATA).hexdigest(),
        "manifest.json",
        "application/json",
    )


def response(data=DATA, version="version-A"):
    return {
        "Body": StreamingBody(io.BytesIO(data), len(data)),
        "ContentLength": len(data),
        "ETag": '"deliberately-not-a-hash"',
        "VersionId": version,
    }


def test_conditional_create_readback_and_exact_pinned_head(backend):
    client, stub = backend
    with stub:
        stub.add_response(
            "put_object",
            {"VersionId": "version-A", "ETag": '"irrelevant"'},
            {
                "Bucket": "owned",
                "Key": KEY,
                "Body": DATA,
                "ContentLength": len(DATA),
                "ContentType": "application/json",
                "IfNoneMatch": "*",
            },
        )
        stub.add_response(
            "get_object", response(), {"Bucket": "owned", "Key": KEY, "VersionId": "version-A"}
        )
        pinned = client.put_new(ref(), io.BytesIO(DATA), multipart=lambda _: pytest.fail())
        assert pinned.version == "version-A"
        stub.add_response(
            "head_object",
            {"VersionId": "version-A", "ContentLength": len(DATA)},
            {"Bucket": "owned", "Key": KEY, "VersionId": "version-A"},
        )
        client.stat(pinned)
        stub.assert_no_pending_responses()


@pytest.mark.parametrize("mode", ["bad-bytes", "wrong-version", "missing-version", "expired"])
def test_pinned_read_fails_closed(backend, mode):
    client, stub = backend
    params = {"Bucket": "owned", "Key": KEY, "VersionId": "version-A"}
    with stub:
        if mode == "bad-bytes":
            stub.add_response("get_object", response(b"x" * len(DATA)), params)
        elif mode == "wrong-version":
            stub.add_response("get_object", response(version="version-B"), params)
        else:
            stub.add_client_error(
                "get_object",
                service_error_code="NoSuchVersion" if mode == "missing-version" else "ExpiredToken",
                http_status_code=404 if mode == "missing-version" else 403,
                expected_params=params,
            )
        with pytest.raises(V2Error) as error:
            client.read_verified(replace(ref(), version="version-A"), io.BytesIO())
        assert error.value.code == ("storage_denied" if mode == "expired" else "integrity_failure")
        stub.assert_no_pending_responses()


@pytest.mark.parametrize("cut", ["initiation", "part", "completion", "none"])
def test_multipart_writes_exactly_once_and_persists_id_before_parts(backend, cut):
    client, stub = backend
    persisted = []
    key = {"Bucket": "owned", "Key": KEY}
    upload = {**key, "UploadId": "multipart-A"}
    with stub:
        init = {**key, "ContentType": "application/json"}
        if cut == "initiation":
            stub.add_client_error(
                "create_multipart_upload",
                service_error_code="SlowDown",
                http_status_code=503,
                expected_params=init,
            )
            with pytest.raises(StorageUnavailable):
                client.begin_multipart(ref(), persisted.append)
            assert not persisted
        else:
            stub.add_response("create_multipart_upload", {"UploadId": "multipart-A"}, init)
            writer = client.begin_multipart(ref(), persisted.append)
            assert persisted == ["multipart-A"]
            writer.write(DATA)
            part = {**upload, "PartNumber": 1, "Body": DATA, "ContentLength": len(DATA)}
            if cut == "part":
                stub.add_client_error(
                    "upload_part",
                    service_error_code="SlowDown",
                    http_status_code=503,
                    expected_params=part,
                )
            else:
                stub.add_response("upload_part", {"ETag": '"part-tag"'}, part)
                complete = {
                    **upload,
                    "IfNoneMatch": "*",
                    "MultipartUpload": {"Parts": [{"ETag": '"part-tag"', "PartNumber": 1}]},
                }
                if cut == "completion":
                    stub.add_client_error(
                        "complete_multipart_upload",
                        service_error_code="SlowDown",
                        http_status_code=503,
                        expected_params=complete,
                    )
                else:
                    stub.add_response(
                        "complete_multipart_upload", {"VersionId": "version-A"}, complete
                    )
                    stub.add_response("get_object", response(), {**key, "VersionId": "version-A"})
            if cut == "none":
                assert writer.complete().version == "version-A"
            else:
                with pytest.raises(StorageUnavailable):
                    writer.complete()
            writer.close()
        stub.assert_no_pending_responses()


@pytest.mark.parametrize(
    ("status", "code", "operation"),
    [
        (301, "Moved", "PutObject"),
        (400, "AuthorizationHeaderMalformed", "PutObject"),
        (400, "PermanentRedirect", "GetObject"),
        (400, "IllegalLocationConstraintException", "PutObject"),
        (400, "400", "HeadObject"),
    ],
)
def test_sdk_region_redirects_are_rejected(status, code, operation):
    with pytest.raises(V2Error, match="redirects are disabled"):
        _reject_redirect(
            (SimpleNamespace(status_code=status), {"Error": {"Code": code}}),
            SimpleNamespace(name=operation),
        )


def test_transport_error_returns_to_durable_retry_without_replaying():
    calls = []

    def fail(**params):
        calls.append(params)
        raise ConnectTimeoutError(endpoint_url="https://secret-endpoint.invalid")

    config = ObjectConfig("archive", "https://unused.invalid", "us-east-1", "owned", "phase6")
    client = S3Backend(config, SimpleNamespace(put_object=fail))
    with pytest.raises(StorageUnavailable, match="temporarily unavailable") as error:
        client.put_new(ref(), io.BytesIO(DATA), multipart=lambda _: pytest.fail())
    assert len(calls) == 1 and "secret-endpoint" not in str(error.value)


def test_owned_client_scope_closes_once_after_operations_and_shared_client_is_retained():
    events = []
    config = ObjectConfig("archive", "https://unused.invalid", "us-east-1", "owned", "phase6")
    client = SimpleNamespace(close=lambda: events.append("closed"))
    owned = S3Backend(config, client, owns_client=True)
    with managed_backend(owned) as selected:
        assert selected is owned and events == []
    owned.close()
    assert events == ["closed"]
    with pytest.raises(V2Error, match="client is closed"):
        owned._run("get_bucket_versioning")
    shared = S3Backend(config, client)
    with pytest.raises(RuntimeError), managed_backend(shared):
        raise RuntimeError("controlled failure")
    assert events == ["closed"]
