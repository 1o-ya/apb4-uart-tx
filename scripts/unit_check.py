"""Run evidence unit tests with a nonempty, exact test-ID execution manifest."""
from __future__ import annotations

import argparse
import contextlib
import json
import sys
import traceback
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PATTERN = "test_*evidence.py"


def suite_ids(suite: unittest.TestSuite) -> list[str]:
    ids: list[str] = []
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            ids.extend(suite_ids(item))
        elif isinstance(item, unittest.TestCase):
            ids.append(item.id())
        else:
            raise TypeError(f"Unexpected discovered test object: {type(item).__name__}")
    return ids


def pass_decision(expected: list[str], executed: list[str], tests_run: int,
                  failures: int = 0, errors: int = 0, skipped: int = 0,
                  expected_failures: int = 0, unexpected_successes: int = 0,
                  stopped: bool = False) -> dict[str, Any]:
    reasons: list[str] = []
    if not expected:
        reasons.append("empty_discovery")
    if len(set(expected)) != len(expected) or len(set(executed)) != len(executed):
        reasons.append("duplicate_test_ids")
    if expected != executed:
        reasons.append("test_id_manifest_mismatch")
    if tests_run != len(expected) or tests_run != len(executed):
        reasons.append("execution_count_mismatch")
    if any((failures, errors, skipped, expected_failures, unexpected_successes)):
        reasons.append("nonpassing_test_outcomes")
    if stopped:
        reasons.append("runner_stopped_early")
    return {"status": "passed" if not reasons else "failed", "reasons": reasons,
            "expected_test_ids": expected, "executed_test_ids": executed,
            "expected_count": len(expected), "tests_run": tests_run,
            "failures": failures, "errors": errors, "skipped": skipped,
            "expected_failures": expected_failures,
            "unexpected_successes": unexpected_successes, "stopped": stopped}


class TrackingResult(unittest.TextTestResult):
    """Record actual started cases rather than trusting a successful exit code."""

    def __init__(self, stream: Any, descriptions: bool, verbosity: int) -> None:
        super().__init__(stream, descriptions, verbosity)
        self.executed_ids: list[str] = []

    def startTest(self, test: unittest.TestCase) -> None:
        super().startTest(test)
        self.executed_ids.append(test.id())


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.write_text(json.dumps(report, indent=2) + "\n")


def execute(out: Path) -> dict[str, Any]:
    report: dict[str, Any] = {"status": "failed", "python": sys.version.split()[0],
                              "discovery_pattern": PATTERN}
    sys.path.insert(0, str(ROOT))
    with (out / "unit.log").open("w") as log:
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            try:
                suite = unittest.TestLoader().discover(str(ROOT / "tests"), pattern=PATTERN)
                expected = suite_ids(suite)
                report.update({"status": "running", "expected_test_ids": expected,
                               "expected_count": len(expected)})
                write_report(out / "verification.json", report)
                runner = unittest.TextTestRunner(stream=log, verbosity=2, resultclass=TrackingResult)
                result = runner.run(suite)
                assert isinstance(result, TrackingResult)
                report.update(pass_decision(expected, result.executed_ids, result.testsRun,
                                           len(result.failures), len(result.errors), len(result.skipped),
                                           len(result.expectedFailures), len(result.unexpectedSuccesses),
                                           result.shouldStop))
            except Exception as exc:
                report.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}"})
                traceback.print_exc(file=log)
    write_report(out / "verification.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = execute(out)
    print(f"{report['status']}: {report.get('tests_run', 0)} evidence unit tests; {out}")
    raise SystemExit(0 if report["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
