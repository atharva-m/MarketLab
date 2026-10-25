"""Read-only paired clock evidence with owned observer cleanup and partial results."""

import argparse
import json
import math
import subprocess
import threading
import time
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import httpx
import sqlalchemy as sa

from marketlab.config import Settings

OWNER = "clock-20261024"
LABEL = "marketlab.clock.owner"


def summary(samples, field):
    values = [int(Decimal(row[field])) for row in samples]
    deltas = [after - before for before, after in zip(values, values[1:], strict=False)]
    return {
        "samples": len(values),
        "negative_steps": sum(delta < 0 for delta in deltas),
        "minimum_step": min(deltas, default=0),
        "elapsed": values[-1] - values[0] if values else 0,
        "negative_examples": [
            {"index": index + 1, "delta": delta} for index, delta in enumerate(deltas) if delta < 0
        ][:30],
    }


def remove_owned(identifier, name):
    """Inspect by known ID or unique name; remove only a verified owned ID."""
    lookup = identifier or name
    inspected = subprocess.run(
        ["docker", "inspect", lookup],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if inspected.returncode:
        inventory = subprocess.run(
            ["docker", "container", "ls", "--all", "--no-trunc", "--format", "{{.ID}}\t{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if inventory.returncode:
            raise RuntimeError("Observer absence not confirmed: Docker inventory failed")
        entries = [line.split("\t", 1) for line in inventory.stdout.splitlines() if line]
        if any(len(parts) != 2 for parts in entries):
            raise RuntimeError("Observer absence not confirmed: invalid inventory")
        present = any(
            container_id == lookup if identifier else container_name == name
            for container_id, container_name in entries
        )
        if present:
            raise RuntimeError("Present observer could not be inspected; cleanup refused")
        return {
            "already_absent": True,
            "absence_confirmed_by": "successful_container_inventory",
            "inspect_exit_code": inspected.returncode,
        }
    items = json.loads(inspected.stdout)
    if len(items) != 1:
        raise RuntimeError("Ambiguous observer inspection")
    item = items[0]
    actual_id = item.get("Id", "")
    if (
        len(actual_id) != 64
        or any(char not in "0123456789abcdef" for char in actual_id)
        or (identifier is not None and actual_id != identifier)
        or item["Name"] != "/" + name
        or item["Config"].get("Labels", {}).get(LABEL) != OWNER
    ):
        raise RuntimeError("Observer ownership mismatch; cleanup refused")
    removed = subprocess.run(
        ["docker", "rm", "--force", actual_id],
        capture_output=True,
        text=True,
        timeout=20,
    )
    if removed.returncode:
        raise RuntimeError("Owned observer removal failed")
    return {"removed_id": actual_id, "name": name, "ownership_verified": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--port", type=int, default=55435)
    parser.add_argument("--observer-image", default="marketlab:local")
    args = parser.parse_args()
    if not 30 <= args.seconds <= 900:
        parser.error("seconds must be 30..900")
    if args.port != 55435:
        parser.error("The owned clock database port must be 55435")
    if not args.observer_image or args.observer_image.startswith("-"):
        parser.error("An explicit existing observer image is required")
    settings = Settings()
    if settings.sqlalchemy_url.host != "127.0.0.1" or settings.sqlalchemy_url.port != args.port:
        parser.error("The configured database must be the owned loopback instance")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    name = "marketlab-clock-observer-" + uuid4().hex[:12]
    native = []
    database = []
    health = []
    native_metadata = {}
    reader_errors = []
    identifier = None
    creation_attempted = False
    process = None
    reader = None
    engine = None
    first = threading.Event()
    result = {
        "status": "failed",
        "observer": name,
        "observer_image": args.observer_image,
        "seconds": args.seconds,
        "native_samples": native,
        "database_samples": database,
        "health": health,
    }
    # The Windows host controls the measured interval and removes the observer.
    # This longer native watchdog bounds its lifetime if the host is terminated.
    watchdog = math.ceil(args.seconds * 1.5 + 60)
    native_code = f"""
import json,pathlib,time
p=pathlib.Path('/sys/devices/system/clocksource/clocksource0/current_clocksource')
metadata={{"clocksource":p.read_text().strip()}}
print(json.dumps({{"metadata":metadata}}),flush=True)
deadline=time.monotonic()+{watchdog}
index=0
while time.monotonic()<deadline:
    row={{
        "index":index,
        "realtime_ns":time.time_ns(),
        "monotonic_ns":time.monotonic_ns(),
        "raw_ns":time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW),
    }}
    print(json.dumps(row),flush=True)
    index+=1
    time.sleep(0.05)
"""
    started = time.perf_counter()
    try:
        creation_attempted = True
        created = subprocess.run(
            [
                "docker",
                "create",
                "--pull",
                "never",
                "-i",
                "--name",
                name,
                "--label",
                LABEL + "=" + OWNER,
                args.observer_image,
                "python",
                "-u",
                "-c",
                native_code,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        identifier = created.stdout.strip()
        if len(identifier) != 64 or any(char not in "0123456789abcdef" for char in identifier):
            raise RuntimeError("Invalid created observer identity")
        result["observer_id"] = identifier
        process = subprocess.Popen(
            ["docker", "start", "--attach", "--interactive", identifier],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        def receive():
            try:
                for line in process.stdout:
                    row = json.loads(line)
                    if "metadata" in row:
                        native_metadata.update(row["metadata"])
                    else:
                        row.update(host_perf_ns=time.perf_counter_ns(), host_wall_ns=time.time_ns())
                        native.append(row)
                        first.set()
            except Exception as error:
                reader_errors.append(type(error).__name__)
                first.set()

        reader = threading.Thread(target=receive, daemon=True)
        reader.start()
        print(
            json.dumps(
                {
                    "phase": "started",
                    "observer": name,
                    "observer_id": identifier,
                    "seconds": args.seconds,
                }
            ),
            flush=True,
        )
        if not first.wait(20) or not native:
            raise RuntimeError("Observer produced no clock samples")
        origin = native[0]["host_perf_ns"]
        deadline = origin + args.seconds * 1_000_000_000
        maximum_end = deadline + 15_000_000_000
        engine = sa.create_engine(
            settings.sqlalchemy_url,
            connect_args=settings.database_connect_args,
        )
        next_health = time.perf_counter()
        with (
            engine.connect() as connection,
            httpx.Client(
                trust_env=False,
                follow_redirects=False,
                timeout=2,
            ) as client,
        ):
            connection.execute(sa.text("SET LOCAL statement_timeout = '5s'"))
            while time.perf_counter_ns() < deadline or native[-1]["host_perf_ns"] < deadline:
                if reader_errors or process.poll() is not None:
                    raise RuntimeError("Observer exited before the host measurement interval")
                if time.perf_counter_ns() > maximum_end:
                    raise RuntimeError("Observer clock stream stopped")
                before = time.perf_counter_ns()
                row = (
                    connection.execute(
                        sa.text(
                            "SELECT (extract(epoch FROM clock_timestamp())*1000000)::text "
                            "AS epoch_us, "
                            "clock_timestamp()::text AS server_text"
                        )
                    )
                    .mappings()
                    .one()
                )
                database.append(
                    {
                        "epoch_us": row["epoch_us"],
                        "server_text": row["server_text"],
                        "host_perf_before_ns": before,
                        "host_perf_ns": time.perf_counter_ns(),
                        "host_wall_ns": time.time_ns(),
                    }
                )
                if time.perf_counter() >= next_health:
                    try:
                        response = client.get("http://127.0.0.1:8000/health/live")
                        health.append(
                            {"host_perf_ns": time.perf_counter_ns(), "status": response.status_code}
                        )
                    except httpx.HTTPError as error:
                        health.append(
                            {"host_perf_ns": time.perf_counter_ns(), "error": type(error).__name__}
                        )
                    next_health = time.perf_counter() + 2
                time.sleep(0.05)
        result["status"] = "completed"
    except BaseException as error:
        result["error_type"] = type(error).__name__
        raise
    finally:
        if engine is not None:
            try:
                engine.dispose()
            except Exception as error:
                result["dispose_error_type"] = type(error).__name__
                result["status"] = "failed"
        try:
            if creation_attempted:
                result["cleanup"] = remove_owned(identifier, name)
        except Exception as error:
            result["cleanup_error_type"] = type(error).__name__
            result["status"] = "failed"
        if process is not None:
            try:
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    process.wait(timeout=5)
            except Exception as error:
                result["client_cleanup_error_type"] = type(error).__name__
                result["status"] = "failed"
            if process.stdin:
                try:
                    process.stdin.close()
                except OSError:
                    pass
        if reader is not None:
            reader.join(timeout=5)
            if reader.is_alive():
                result["reader_did_not_finish"] = True
                result["status"] = "failed"
        if process is not None:
            for stream in (process.stdout, process.stderr):
                if stream:
                    try:
                        stream.close()
                    except OSError:
                        pass
        result["host_elapsed_seconds"] = time.perf_counter() - started
        result["native_metadata"] = native_metadata
        result["reader_errors"] = reader_errors
        try:
            clock_summary = {
                field: summary(native, field)
                for field in (
                    "realtime_ns",
                    "monotonic_ns",
                    "raw_ns",
                    "host_perf_ns",
                    "host_wall_ns",
                )
            }
            result["summary"] = {
                "native": clock_summary,
                "database": summary(database, "epoch_us"),
                "host_database_perf": summary(database, "host_perf_ns"),
                "health_samples": len(health),
                "health_all_200": bool(health) and all(row.get("status") == 200 for row in health),
            }
            if len(native) >= 2:
                windows = clock_summary["host_perf_ns"]["elapsed"]
                raw = clock_summary["raw_ns"]["elapsed"]
                result["summary"].update(
                    {
                        "native_host_span_seconds": windows / 1_000_000_000,
                        "native_raw_to_windows_ratio": raw / windows,
                        "native_monotonic_to_windows_ratio": clock_summary["monotonic_ns"][
                            "elapsed"
                        ]
                        / windows,
                        "native_monotonic_to_raw_ratio": clock_summary["monotonic_ns"]["elapsed"]
                        / raw,
                    }
                )
        except Exception as error:
            result["summary_error_type"] = type(error).__name__
            result["status"] = "failed"
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {
                    "status": result["status"],
                    "output": str(args.output),
                    "summary": result.get("summary"),
                }
            ),
            flush=True,
        )

    if result["status"] != "completed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
