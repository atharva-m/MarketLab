"""One-request, bounded TLS forwarding for the owned AWS outage acceptance case.

No credentials, request bytes, upstream names or exception text are logged.
The caller must separately qualify the exact AWS origin and owned namespace.
"""

import re
import socket
import socketserver
import ssl
import threading
import time
from contextlib import suppress
from urllib.parse import parse_qsl, quote, unquote_to_bytes, urlsplit

HEADER_LIMIT = 32 * 1024
BODY_LIMIT = 16 * 1024**2
WORKERS = 4


class Rejected(Exception):
    """Only constant, non-sensitive errors may cross the proxy boundary."""


class Namespace:
    def __init__(self, endpoint, region, bucket, prefix):
        parsed = urlsplit(endpoint)
        expected = f"s3.{region}.amazonaws.com"
        if (
            parsed.scheme != "https"
            or parsed.netloc != expected
            or parsed.hostname != expected
            or parsed.port not in {None, 443}
            or parsed.path
            or parsed.query
            or parsed.fragment
            or not re.fullmatch(r"[a-z]{2}(?:-[a-z]+)+-\d", region)
            or not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", bucket)
            or not prefix
            or any(part in {"", ".", ".."} for part in prefix.split("/"))
            or not re.fullmatch(r"[A-Za-z0-9_.=/~-]+", prefix)
        ):
            raise Rejected("Unqualified forwarding namespace")
        self.host = expected
        self.bucket_path = "/" + bucket
        self.prefix_path = self.bucket_path + "/" + prefix + "/"

    def target(self, method, target):
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc or parsed.fragment or not target.startswith("/"):
            raise Rejected("Invalid request target")
        try:
            path = unquote_to_bytes(parsed.path).decode("utf-8")
            pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=False)
        except (UnicodeError, ValueError):
            raise Rejected("Invalid request target") from None
        if (
            quote(path, safe="/-._~") != parsed.path
            or re.search(r"%(?![0-9a-fA-F]{2})", parsed.query)
            or any(
                not item or ("=" not in item and item not in {"uploads", "versioning"})
                for item in parsed.query.split("&")
                if parsed.query
            )
            or any(part in {".", "..", ""} for part in path.split("/")[1:])
            or len(pairs) != len(dict(pairs))
            or any(
                len(value) > 4096 or any(ord(c) < 32 or ord(c) > 126 for c in value)
                for _, value in pairs
            )
        ):
            raise Rejected("Invalid request target")
        query = dict(pairs)
        if path == self.bucket_path:
            if method == "GET" and query == {"versioning": ""}:
                return
            raise Rejected("Bucket operation forbidden")
        if not path.startswith(self.prefix_path) or path == self.prefix_path:
            raise Rejected("Object namespace forbidden")
        keys = set(query)
        allowed = (
            (method in {"GET", "HEAD"} and keys in (set(), {"versionId"}))
            or (method == "PUT" and keys in (set(), {"uploadId", "partNumber"}))
            or (method == "POST" and (query == {"uploads": ""} or keys == {"uploadId"}))
            or (method == "DELETE" and keys in ({"versionId"}, {"uploadId"}))
        )
        if (
            not allowed
            or any(not value for key, value in pairs if key != "uploads")
            or ("partNumber" in query and not re.fullmatch(r"[1-9]\d{0,3}", query["partNumber"]))
        ):
            raise Rejected("Object operation forbidden")

    def header(self, header):
        try:
            lines = header.decode("ascii").split("\r\n")
            method, target, protocol = lines[0].split(" ")
            pairs = [line.split(":", 1) for line in lines[1:] if line]
            if any(len(pair) != 2 for pair in pairs):
                raise ValueError
            names = [name.lower() for name, _ in pairs]
            if len(names) != len(set(names)) or any(
                not re.fullmatch(r"[a-z0-9-]+", name) for name in names
            ):
                raise ValueError
            headers = {name.lower(): value.strip() for name, value in pairs}
            length = headers.get("content-length", "0")
            if (
                protocol != "HTTP/1.1"
                or headers.get("host") != self.host
                or headers.get("connection", "").lower() != "close"
                or any(name in headers for name in ("transfer-encoding", "expect", "trailer"))
                or any("\r" in value or "\n" in value for value in headers.values())
                or not re.fullmatch(r"0|[1-9]\d{0,8}", length)
                or int(length) > BODY_LIMIT
                or not headers.get("authorization", "").startswith("AWS4-HMAC-SHA256 ")
                or not re.search(
                    r"(?:^|[ ,])SignedHeaders=(?:[a-z0-9-]+;)*host(?:;[a-z0-9-]+)*(?:,|$)",
                    headers.get("authorization", ""),
                )
            ):
                raise ValueError
            self.target(method, target)
            return int(length)
        except (UnicodeError, ValueError):
            raise Rejected("Invalid request framing") from None


class Drop:
    def __init__(self, server):
        self.server = server
        self.event = threading.Event()

    def is_set(self):
        return self.event.is_set()

    def set(self):
        self.event.set()
        self.server.close_active()

    def clear(self):
        self.event.clear()


class OwnedHTTPSProxy(socketserver.ThreadingTCPServer):
    daemon_threads = False
    block_on_close = True
    request_queue_size = WORKERS

    def __init__(self, namespace):
        self.namespace = namespace
        self.slots = threading.BoundedSemaphore(WORKERS)
        self.lock = threading.Lock()
        self.active = set()
        self.workers = 0
        self.rejected = 0
        self.completed = 0
        super().__init__(("127.0.0.1", 0), Forward)
        self.drop = Drop(self)

    def process_request(self, request, address):
        if self.drop.is_set() or not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        with self.lock:
            self.active.add(request)
            self.workers += 1
        try:
            super().process_request(request, address)
        except BaseException:
            self.release(request)
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.release(request)

    def release(self, request):
        with self.lock:
            self.active.discard(request)
            self.workers -= 1
        self.slots.release()

    def close_active(self):
        with self.lock:
            for active in self.active:
                with suppress(OSError):
                    active.shutdown(socket.SHUT_RDWR)
                with suppress(OSError):
                    active.close()

    def handle_error(self, request, address):
        # socketserver's default handler prints raw exceptions/addresses.
        with self.lock:
            self.rejected += 1

    def sign(self, request, **_):
        parsed = urlsplit(request.url)
        if parsed.scheme != "http" or parsed.netloc != f"127.0.0.1:{self.server_address[1]}":
            raise Rejected("Unexpected proxy client endpoint")
        self.namespace.target(
            request.method, parsed.path + ("?" + parsed.query if parsed.query else "")
        )
        request.headers["Host"] = self.namespace.host
        request.headers["Connection"] = "close"
        if "Expect" in request.headers:
            del request.headers["Expect"]


class Forward(socketserver.BaseRequestHandler):
    def handle(self):
        server = self.server
        deadline = time.monotonic() + 60
        upstream = None
        try:
            self.request.settimeout(5)
            data = bytearray()
            while b"\r\n\r\n" not in data:
                chunk = self.request.recv(min(4096, HEADER_LIMIT + 1 - len(data)))
                if not chunk or len(data) + len(chunk) > HEADER_LIMIT or server.drop.is_set():
                    raise Rejected("Request header unavailable")
                data.extend(chunk)
            header, body = bytes(data).split(b"\r\n\r\n", 1)
            remaining = server.namespace.header(header) - len(body)
            if remaining < 0:
                raise Rejected("Pipelined request forbidden")
            if server.drop.is_set():
                return
            raw = socket.create_connection((server.namespace.host, 443), timeout=5)
            try:
                upstream = ssl.create_default_context().wrap_socket(
                    raw, server_hostname=server.namespace.host
                )
            except BaseException:
                raw.close()
                raise
            with server.lock:
                server.active.add(upstream)
            if server.drop.is_set():
                return
            upstream.settimeout(5)
            upstream.sendall(header + b"\r\n\r\n" + body)
            while remaining:
                if server.drop.is_set() or time.monotonic() >= deadline:
                    return
                chunk = self.request.recv(min(64 * 1024, remaining))
                if not chunk:
                    raise Rejected("Request body unavailable")
                remaining -= len(chunk)
                upstream.sendall(chunk)
            # Never relay a second request on this connection, including pipelining.
            self.request.setblocking(False)
            try:
                if self.request.recv(1, socket.MSG_PEEK):
                    raise Rejected("Pipelined request forbidden")
            except BlockingIOError:
                pass
            finally:
                self.request.settimeout(5)
            upstream.settimeout(30)
            while not server.drop.is_set() and time.monotonic() < deadline:
                chunk = upstream.recv(64 * 1024)
                if not chunk:
                    with server.lock:
                        server.completed += 1
                    return
                self.request.sendall(chunk)
        except (OSError, Rejected, ValueError):
            with server.lock:
                server.rejected += 1
        finally:
            if upstream is not None:
                with server.lock:
                    server.active.discard(upstream)
                upstream.close()
