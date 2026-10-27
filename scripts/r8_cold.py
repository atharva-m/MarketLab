"""Fresh-process R8 cold62 acceptance using retained verifier assertions unchanged.

Only explicit owned-settings/output adapters are rebound. Numerical acceptance,
full per-version verification, exact hashes, worker readiness/drain and <1800s
remain in the retained production-facing verifier harness. Outer resource evidence
measures this process, children and owned database/cache throughout invocation.
"""

import argparse
import asyncio
import json
from pathlib import Path

import verifier_acceptance as verifier
from r8_common import (
    BASE,
    ROOT,
    Invocation,
    Sampler,
    owned_settings,
    recorded,
    validate_prefix,
)

from marketlab.datasets.source import file_hash


async def cold(prefix: str) -> None:
    prefix = validate_prefix(prefix)
    output = BASE / f"{prefix}-cold.json"
    if await asyncio.to_thread(output.exists):
        raise FileExistsError("R8 cold evidence prefix already exists")
    settings = owned_settings()
    resources = {
        kind: {
            "id": recorded(kind)["Id"],
            "name": recorded(kind)["Name"],
            "image": recorded(kind)["Image"],
        }
        for kind in ("postgres", "redis")
    }
    verifier.BASE = BASE
    verifier.ROOT = ROOT
    verifier.owned_settings = lambda: (settings, resources)
    with (
        Invocation(prefix, "cold62") as evidence,
        Sampler(BASE / f"{prefix}-cold62-resources.json"),
    ):
        evidence.data.update(
            resource_evidence=str(BASE / f"{prefix}-cold62-resources.json"),
            verifier_evidence=str(output),
            script_sha256=file_hash(Path(__file__)),
            verifier_script_sha256=file_hash(Path(verifier.__file__)),
            instrumentation="Owned settings/output adapter only; unchanged verifier assertions",
            gpu_scope="Numerical-only CPU workflow; no inference or GPU work requested",
        )
        await verifier.cold(prefix)
        result = json.loads(await asyncio.to_thread(output.read_text))
        assert result["status"] == "passed"
        assert result["catalog"] == {"partitions": 62, "rows": 230311900}
        assert result["whole_workflow_seconds"] < 1800
        assert result["numerical_attempts"] == 1
        assert result["memo"] == {"state": "queued", "attempts": 0, "model_calls": 0}
        evidence.data.update(
            whole_workflow_including_cleanup_seconds=result["whole_workflow_seconds"],
            cleanup_seconds=result["phases"]["cleanup_seconds"],
            workflow_excluding_cleanup_seconds=result["whole_workflow_seconds"]
            - result["phases"]["cleanup_seconds"],
            catalog=result["catalog"],
            results_sha256=result["results_sha256"],
            summary_sha256=result["summary_sha256"],
            original_legacy_memory_fields=(
                "Legacy verifier measurements remain unmeasured; mandatory outer resource "
                "measurements are separate and linked."
            ),
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", required=True, type=validate_prefix)
    args = parser.parse_args()
    asyncio.run(cold(args.prefix))


if __name__ == "__main__":
    main()
