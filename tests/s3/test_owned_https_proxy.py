"""Offline guards for the test-only proxy; no endpoint or credential access."""

from types import SimpleNamespace

import pytest
from botocore.awsrequest import AWSRequest
from owned_https_proxy import Namespace, OwnedHTTPSProxy, Rejected

pytestmark = pytest.mark.s3
HOST = "s3.us-east-1.amazonaws.com"


def namespace():
    return Namespace("https://" + HOST, "us-east-1", "synthetic-bucket", "owned/run")


def header(target="/synthetic-bucket/owned/run/object", method="GET", extra=""):
    return (
        f"{method} {target} HTTP/1.1\r\nHost: {HOST}\r\nConnection: close\r\n"
        "Authorization: AWS4-HMAC-SHA256 Credential=synthetic, "
        "SignedHeaders=host;x-amz-date, Signature=synthetic\r\n" + extra
    ).encode("ascii")


@pytest.mark.parametrize(
    ("method", "target"),
    [
        ("GET", "/synthetic-bucket?versioning"),
        ("PUT", "/synthetic-bucket/owned/run/object"),
        ("POST", "/synthetic-bucket/owned/run/object?uploads"),
        ("PUT", "/synthetic-bucket/owned/run/object?uploadId=one&partNumber=1"),
        ("POST", "/synthetic-bucket/owned/run/object?uploadId=one"),
        ("HEAD", "/synthetic-bucket/owned/run/object?versionId=one%2Btwo"),
        ("DELETE", "/synthetic-bucket/owned/run/object?versionId=one"),
    ],
)
def test_exact_owned_operation_shapes(method, target):
    assert namespace().header(header(target, method)) == 0


@pytest.mark.parametrize(
    "target",
    [
        "https://other.invalid/synthetic-bucket/owned/run/object",
        "/synthetic-bucket/other/object",
        "/synthetic-bucket/owned/run/../other",
        "/synthetic-bucket/owned/run/%2e%2e/other",
        "/synthetic-bucket/owned%2Frun/object",
        "/synthetic-bucket/owned/run//object",
        "/synthetic-bucket/owned/run/object?list-type=2",
        "/synthetic-bucket/owned/run/object?versionId=one&versionId=two",
        "/synthetic-bucket/owned/run/object?versionId=%QQ",
        "/synthetic-bucket/owned/run/object?versionId=one&",
        "/synthetic-bucket?prefix=owned/run",
    ],
)
def test_other_targets_fail_closed(target):
    with pytest.raises(Rejected):
        namespace().header(header(target))


@pytest.mark.parametrize(
    "extra",
    [
        "Content-Length: 1\r\nContent-Length: 1\r\n",
        "Content-Length: 16777217\r\n",
        "Content-Length: -1\r\n",
        "Transfer-Encoding: chunked\r\n",
        "Expect: 100-continue\r\n",
        "Host: other.invalid\r\n",
        " Bad-Fold: value\r\n",
    ],
)
def test_ambiguous_or_unbounded_framing_fails_closed(extra):
    with pytest.raises(Rejected):
        namespace().header(header(extra=extra))


def test_only_reviewed_regional_origin_is_accepted():
    for endpoint in ("https://other.invalid", "http://" + HOST, "https://" + HOST + "/path"):
        with pytest.raises(Rejected):
            Namespace(endpoint, "us-east-1", "synthetic-bucket", "owned/run")


def test_sign_hook_preserves_remote_host_and_forces_one_request_without_network():
    proxy = SimpleNamespace(namespace=namespace(), server_address=("127.0.0.1", 12345))
    request = AWSRequest(
        method="PUT",
        url="http://127.0.0.1:12345/synthetic-bucket/owned/run/object",
        headers={"Expect": "100-continue"},
        data=b"body",
    )
    OwnedHTTPSProxy.sign(proxy, request)
    assert request.headers["Host"] == HOST
    assert request.headers["Connection"] == "close" and "Expect" not in request.headers
    request.url = "http://other.invalid/synthetic-bucket/owned/run/object"
    with pytest.raises(Rejected):
        OwnedHTTPSProxy.sign(proxy, request)
