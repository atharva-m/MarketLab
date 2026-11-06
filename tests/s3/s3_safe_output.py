"""Bounded memory capture and defensive redaction for owned S3 test children."""

import base64
import json
import os
import re
import subprocess
import sys
import threading
from pathlib import Path
from urllib.parse import quote, quote_plus

LIMIT = 8 * 1024**2
KEYS = (
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_DEFAULT_REGION",
    "S3_BUCKET_NAME",
    "AWS_SESSION_TOKEN",
    "MARKETLAB_STORAGE_S3_ACCESS_KEY",
    "MARKETLAB_STORAGE_S3_SECRET_KEY",
    "MARKETLAB_STORAGE_S3_REGION",
    "MARKETLAB_STORAGE_S3_BUCKET",
    "MARKETLAB_STORAGE_S3_SESSION_TOKEN",
    "MARKETLAB_PHASE6_RESTORE_S3_ACCESS_KEY",
    "MARKETLAB_PHASE6_RESTORE_S3_SECRET_KEY",
    "MARKETLAB_PHASE6_RESTORE_S3_SESSION_TOKEN",
    "MARKETLAB_PHASE6_RESTORE_S3_REGION",
    "MARKETLAB_PHASE6_RESTORE_S3_BUCKET",
    "MARKETLAB_PHASE6_EXPIRED_S3_ACCESS_KEY",
    "MARKETLAB_PHASE6_EXPIRED_S3_SECRET_KEY",
    "MARKETLAB_PHASE6_EXPIRED_S3_SESSION_TOKEN",
)


def protected_values(additional=()):
    extra = json.loads(os.environ.get("MARKETLAB_PHASE6_REDACTION_VALUES", "[]"))
    if (
        not isinstance(extra, list)
        or len(extra) > 64
        or any(not isinstance(value, str) or not 1 <= len(value) <= 16384 for value in extra)
    ):
        raise AssertionError("Private redaction context is malformed")
    return tuple(
        sorted(
            {*(os.environ[key] for key in KEYS if os.environ.get(key)), *extra, *additional},
            key=len,
            reverse=True,
        )
    )


def character(char):
    code = ord(char)
    choices = [re.escape(char), rf"\\{{1,4}}u(?i:{code:04x})", rf"&#{code};", rf"&#(?i:x{code:x});"]
    if code <= 255:
        choices.extend(
            (rf"\\{{1,4}}x(?i:{code:02x})", "".join(f"%(?i:{byte:02x})" for byte in char.encode()))
        )
    if char == "/":
        choices.append(r"\\{1,4}/")
    if char == " ":
        choices.append(r"\+")
    return "(?:" + "|".join(choices) + ")"


def redact_text(text, additional=()):
    if not isinstance(text, str):
        raise AssertionError("Captured output must be decoded in memory")
    for value in protected_values(additional):
        if not value:
            continue
        # Per-character alternatives also remove mixed raw/percent/Unicode/hex
        # escape representations, rather than matching just one whole encoding.
        text = re.sub("".join(character(char) for char in value), "<redacted>", text)
        encoded = value.encode()
        forms = {
            quote(value, safe=""),
            quote_plus(value),
            repr(value)[1:-1],
            json.dumps(value)[1:-1],
            base64.b64encode(encoded).decode(),
            base64.urlsafe_b64encode(encoded).decode(),
        }
        for form in sorted(forms, key=len, reverse=True):
            if form:
                text = text.replace(form, "<redacted>")
    return text


class MemoryCapture:
    """An inherited anonymous pipe; no raw child output reaches a disk file."""

    def __init__(self, limit=LIMIT):
        self.limit = limit
        self.buffer = bytearray()
        self.overflow = False
        self.read_error = False
        reader, writer = os.pipe()
        os.set_inheritable(reader, False)
        self.writer = os.fdopen(writer, "wb", buffering=0)
        self.reader = os.fdopen(reader, "rb", buffering=0)
        self.thread = threading.Thread(target=self._read, name="owned-s3-output", daemon=True)
        self.thread.start()

    def _read(self):
        try:
            with self.reader:
                while chunk := self.reader.read(64 * 1024):
                    remaining = self.limit - len(self.buffer)
                    self.buffer.extend(chunk[:remaining])
                    self.overflow |= len(chunk) > remaining
        except OSError:
            self.read_error = True

    def finish(self):
        self.writer.close()
        self.thread.join(timeout=5)
        if self.thread.is_alive() or self.read_error:
            raise AssertionError("Owned in-memory output reader did not drain")
        if self.overflow:
            raise AssertionError("Owned in-memory output exceeded its bound")

    def sanitized(self):
        if self.thread.is_alive():
            raise AssertionError("Owned output must drain before redaction")
        if self.overflow or self.read_error:
            return "Owned child output unavailable: bounded capture failed.\n"
        return redact_text(self.buffer.decode("utf-8", errors="replace"))


def python_command(args):
    bootstrap = Path(__file__).with_name("guarded_python.py")
    if os.environ.get("MARKETLAB_PHASE6_BOOTSTRAP_ACTIVE") != "guarded-python-v1":
        raise AssertionError("Owned Python entrypoint was not explicitly guarded")
    return [sys.executable, "-I", "-S", str(bootstrap), "--", *args]


class BoundedChild:
    """The fault fixture's existing process control with bounded private output."""

    def __init__(self, args):
        self.output = MemoryCapture()
        try:
            self.child = subprocess.Popen(
                python_command(args), stdout=self.output.writer, stderr=subprocess.STDOUT
            )
        except BaseException:
            self.output.finish()
            raise
        self.args = self.child.args
        self.done = False

    @property
    def returncode(self):
        return self.child.returncode

    def poll(self):
        return self.child.poll()

    def kill(self):
        self.child.kill()

    def communicate(self, timeout):
        self.child.wait(timeout=timeout)
        if not self.done:
            self.done = True
            self.output.finish()
        return self.output.sanitized(), ""

    def close(self):
        if self.child.poll() is None:
            raise AssertionError("Owned child must drain before output close")
        if not self.done:
            self.done = True
            self.output.finish()


def run_python(args, timeout):
    child = BoundedChild(args)
    try:
        stdout, stderr = child.communicate(timeout)
        return subprocess.CompletedProcess(child.args, child.returncode, stdout, stderr)
    finally:
        if child.child.poll() is None:
            child.kill()
        if not child.done:
            child.communicate(10)
        child.close()
