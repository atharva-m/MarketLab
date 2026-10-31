"""Private admission context and fail-closed public verifier-pool child binding."""

import json
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from sqlalchemy.engine import Engine

from . import native_identity
from .common import V2Error, canonical_json
from .core import execute, one, transaction

_CONTEXT: ContextVar[tuple[Engine, dict[str, Any]] | None] = ContextVar(
    "v2_native_admission", default=None
)


@contextmanager
def scope(engine: Engine, ticket: dict[str, Any] | None) -> Any:
    token = _CONTEXT.set(None if ticket is None else (engine, ticket))
    try:
        yield
    finally:
        _CONTEXT.reset(token)


def envelope(value: dict[str, Any]) -> dict[str, Any] | None:
    if native_identity.valid(value):
        return {
            "schema": "native-ticket-v1",
            "process": value,
            "children_pending": False,
            "children": [],
        }
    if (
        set(value) != {"schema", "process", "children_pending", "children"}
        or value["schema"] != "native-ticket-v1"
        or type(value["children_pending"]) is not bool
        or not isinstance(value["process"], dict)
        or not native_identity.valid(value["process"])
        or not isinstance(value["children"], list)
        or len(value["children"]) > 8
        or any(
            not isinstance(child, dict) or not native_identity.valid(child)
            for child in value["children"]
        )
    ):
        return None
    identities = [(child["pid"], child["birth"]) for child in value["children"]]
    if len(set(identities)) != len(identities):
        return None
    if any(
        child["host"] != value["process"]["host"]
        or child["boot"] != value["process"]["boot"]
        or child["executable"] != value["process"]["executable"]
        for child in value["children"]
    ):
        return None
    return value


def dead(value: dict[str, Any]) -> bool:
    parsed = envelope(value)
    if parsed is not None and parsed["children_pending"]:
        # A direct same-machine new OS boot proves every old process died,
        # including a child whose identity could not be registered before loss.
        return native_identity.rebooted(parsed["process"])
    return (
        parsed is not None
        and not parsed["children_pending"]
        and native_identity.dead(parsed["process"])
        and all(native_identity.dead(child) for child in parsed["children"])
    )


def alive(value: dict[str, Any]) -> bool:
    parsed = envelope(value)
    return parsed is not None and native_identity.alive(parsed["process"])


def pending(value: dict[str, Any]) -> bool:
    parsed = envelope(value)
    return parsed is None or parsed["children_pending"]


def _update(children: list[dict[str, Any]] | None) -> None:
    context = _CONTEXT.get()
    if context is None:
        return
    engine, ticket = context
    with transaction(engine) as connection:
        row = one(
            connection,
            "SELECT native_identity FROM v2_admission_tickets "
            "WHERE ticket_id=:id AND owner=:owner AND state IN ('pending','active','draining') "
            "FOR UPDATE",
            id=ticket["ticket_id"],
            owner=ticket["owner"],
        )
        if row is None:
            raise V2Error("ownership_lost", "Native child admission unavailable")
        parsed = envelope(json.loads(row["native_identity"]))
        if parsed is None or not native_identity.same(parsed["process"]):
            raise V2Error("ownership_lost", "Native child parent identity mismatch")
        parsed["children_pending"] = children is None
        if children is not None:
            merged = {(child["pid"], child["birth"]): child for child in parsed["children"]}
            merged.update({(child["pid"], child["birth"]): child for child in children})
            parsed["children"] = list(merged.values())
        if envelope(parsed) is None:
            raise V2Error("unavailable", "Native child admission exceeds its bound")
        execute(
            connection,
            "UPDATE v2_admission_tickets SET native_identity=:native,"
            "updated_at=clock_timestamp() WHERE ticket_id=:id",
            id=ticket["ticket_id"],
            native=canonical_json(parsed).decode(),
        )


def launch_guard() -> None:
    # Durable intent precedes public executor startup. Parent death in the gap
    # cannot be interpreted as a childless, recoverable ticket.
    _update(None)


def register(pids: list[int]) -> None:
    if _CONTEXT.get() is None:
        return
    if not 1 <= len(pids) <= 2 or len(set(pids)) != len(pids):
        raise V2Error("unavailable", "Verifier child set is incomplete")
    identities = [native_identity.child(pid) for pid in pids]
    _update(identities)
