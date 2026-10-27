"""No-model R8 source compatibility gate on the fixed fresh owned profile.

Run only after timed/model workloads quiesce. Combines existing R2 incompatible
contract and R4 mismatch cases, four real retry R5/R6 old-pin cases, and retained
R4 numerical read/rejection acceptance. No original or runtime changes.
"""

import argparse
import asyncio
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from r8_common import BASE, PROFILE, Invocation, owned_settings, validate_prefix
from r8_finish import environment
from r8_recovery import durability_adapter

TEST = Path("tests/test_r8_source_compatibility_integration.py")
OLD = Path("artifacts/r8/runtime-freeze.json")
EXPECTED_CASES = {"copilot-provenance", "copilot-validated", "memo-pin", "memo-validated"}


def run(prefix):
    prefix = validate_prefix(prefix)
    if PROFILE.name != "adoption-20261027":
        raise ValueError("Select fixed adoption-20261027 resource profile")
    with Invocation(prefix, "source-compatibility") as evidence:
        settings = owned_settings()
        old = json.loads(OLD.read_text())
        if old == evidence.data["execution"]:
            raise RuntimeError(
                "Source compatibility requires genuinely different retained identity"
            )
        root = BASE / (prefix + "-source-cases")
        root.mkdir(exist_ok=False)
        evidence.data.update(
            script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            tests_sha256=hashlib.sha256(TEST.read_bytes()).hexdigest(),
            old_identity_file_sha256=hashlib.sha256(OLD.read_bytes()).hexdigest(),
            old_execution=old,
            model_dispatches=0,
            measurement_scope="Persisted-state compatibility; no model/resource benchmark claim",
        )
        env = {**environment(settings), "MARKETLAB_R8_SOURCE_EVIDENCE": str(root.resolve())}
        command = [
            sys.executable,
            "-m",
            "pytest",
            "-m",
            "integration",
            "-vv",
            str(TEST),
            "tests/test_jobs_integration.py::test_incompatible_execution_contract_is_not_claimed",
            "tests/test_research_integration.py::test_worker_fingerprint_mismatch_is_terminal",
            "--basetemp=" + str(BASE / (prefix + "-pytest")),
        ]
        log = BASE / (prefix + "-source-tests.log")
        with log.open("x", encoding="utf-8") as output:
            result = subprocess.run(command, env=env, stdout=output, stderr=output, timeout=240)
        evidence.data.update(command=command, test_exit_code=result.returncode, test_log=str(log))
        evidence.flush()
        if result.returncode:
            raise AssertionError("Real PostgreSQL source compatibility tests failed")
        cases = {path.stem: json.loads(path.read_text()) for path in root.glob("*.json")}
        if set(cases) != EXPECTED_CASES:
            raise AssertionError(
                "All four actual retained-source case receipts required; skips are incomplete"
            )
        for case in cases.values():
            if not (
                case["status"] == "passed"
                and case["old_execution"] == old
                and case["current_execution"] == evidence.data["execution"]
                and case["model_identifications"] == case["new_model_calls"] == 0
                and case["timestamp_edits"] == 0
            ):
                raise AssertionError("Source compatibility case evidence mismatch")
        evidence.data["cases"] = cases
        adapter = durability_adapter("r5_acceptance")
        evidence.data["retained_adapter"] = adapter.adapter_provenance
        evidence.flush()
        asyncio.run(adapter.retained_results(prefix))
        retained = json.loads((BASE / (prefix + "-retained-results.json")).read_text())
        if not (
            retained["status"] == "passed"
            and len(retained["readbacks"]) == 10
            and retained["incompatible_queued_refused"]["state"] == "failed"
            and retained["incompatible_queued_refused"]["attempt_count"] == 1
        ):
            raise AssertionError("Retained readback/actual old-fingerprint rejection incomplete")
        evidence.data["retained_results"] = retained
        evidence.data["R2_scope"] = (
            "daily-ingestion-v1 execution-contract incompatibility, not Git SHA pinning"
        )
        evidence.data["clock_scope"] = (
            "Real ten-second retry eligibility; no timestamp edits or unrelated lease-clock suite"
        )
        print(
            json.dumps(
                {
                    "status": "passed",
                    "source_cases": len(cases),
                    "retained_readbacks": 10,
                    "model_dispatches": 0,
                }
            ),
            flush=True,
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", required=True, type=validate_prefix)
    args = parser.parse_args()
    run(args.prefix)


if __name__ == "__main__":
    main()
