"""Inject twelve specific UART faults and require named assertion failures."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.verify import command  # noqa: E402

TEST_NAMES = (
    "test_a_z_and_all_bytes", "test_busy_backpressure_and_back_to_back",
    "test_strobes_protection_and_bus_gating", "test_access_errors_have_no_side_effects",
    "test_async_reset_aborts_and_recovers", "test_async_reset_during_stalled_write",
    "test_held_setup_signals_have_no_side_effects", "test_demo_a_z",
)


@dataclass(frozen=True)
class Mutation:
    candidate_id: str
    before: str
    after: str
    expected_test: str
    baud: int = 100_000


MUTATIONS = (
    Mutation("baud_early", "LAST_COUNT = CLKS_PER_BIT - 1;",
             "LAST_COUNT = CLKS_PER_BIT - 2;", TEST_NAMES[0]),
    Mutation("rounding_floor", "(64'd1 * CLK_FREQ_HZ + SAFE_BAUD / 2) / SAFE_BAUD;",
             "(64'd1 * CLK_FREQ_HZ) / SAFE_BAUD;", TEST_NAMES[0], 400_000),
    Mutation("start_high", "state     <= START;\n                        tx        <= 1'b0;",
             "state     <= START;\n                        tx        <= 1'b1;", TEST_NAMES[0]),
    Mutation("first_bit_msb", "tx    <= shift_reg[0];", "tx    <= shift_reg[7];", TEST_NAMES[0]),
    Mutation("stop_low", "state <= STOP;\n                            tx    <= 1'b1;",
             "state <= STOP;\n                            tx    <= 1'b0;", TEST_NAMES[0]),
    Mutation("ignore_low_strobe", "!pslverr && pwrite && (paddr == DATA_REG) && pstrb[0];",
             "!pslverr && pwrite && (paddr == DATA_REG) && 1'b1;", TEST_NAMES[2]),
    Mutation("no_busy_backpressure", "else if (pstrb[0] && busy)\n                        pready = 1'b0;",
             "else if (pstrb[0] && busy)\n                        pready = 1'b1;", TEST_NAMES[1]),
    Mutation("high_address_alias", "case (paddr)", "case ({16'b0, paddr[15:0]})", TEST_NAMES[3]),
    Mutation("suppress_access_error", "default: pslverr = 1'b1;",
             "default: pslverr = 1'b0;", TEST_NAMES[3]),
    Mutation("setup_response_enabled", "if (rst_n && psel && penable) begin",
             "if (rst_n && psel) begin", TEST_NAMES[6]),
    Mutation("busy_ends_before_stop", "wire busy = (state != IDLE);",
             "wire busy = (state != IDLE) && (state != STOP);", TEST_NAMES[0]),
    Mutation("reset_tx_low", "bit_index <= 3'b0;\n            tx        <= 1'b1;",
             "bit_index <= 3'b0;\n            tx        <= 1'b0;", TEST_NAMES[4]),
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mutate(source: str, mutation: Mutation) -> str:
    matches = source.count(mutation.before)
    if matches != 1:
        raise ValueError(f"{mutation.candidate_id}: expected one source anchor, found {matches}")
    if mutation.before == mutation.after:
        raise ValueError("Mutation must change the source")
    return source.replace(mutation.before, mutation.after, 1)


def inspect_xml(path: Path, returncode: int, expected_test: str | None) -> dict[str, Any]:
    if returncode == 124:
        return {"classification": "timeout", "killed": False}
    if returncode not in (0, 1) or not path.is_file():
        return {"classification": "infrastructure_failure", "killed": False}
    try:
        cases = list(ET.parse(path).getroot().iter("testcase"))
    except ET.ParseError:
        return {"classification": "malformed_results", "killed": False}
    names = [case.get("name") for case in cases]
    if len(names) != len(TEST_NAMES) or set(names) != set(TEST_NAMES):
        return {"classification": "incomplete_results", "killed": False, "tests": len(names)}
    failures: list[dict[str, str | None]] = []
    for case in cases:
        if case.find("skipped") is not None:
            return {"classification": "skipped_results", "killed": False}
        for tag in ("failure", "error"):
            error = case.find(tag)
            if error is not None:
                failures.append({"test": case.get("name"), "type": error.get("error_type"),
                                 "message": error.get("error_msg", error.text or "")})
    assertions_only = all(f["type"] == "AssertionError" for f in failures)
    expected_failed = any(f["test"] == expected_test for f in failures)
    killed = bool(failures) and assertions_only and expected_failed
    if killed:
        classification = "killed"
    elif failures or returncode != 0:
        classification = "unexpected_failure"
    else:
        classification = "survived" if expected_test else "baseline_passed"
    return {"classification": classification, "killed": killed,
            "tests": len(cases), "failures": failures}


def run_case(source: str, out: Path, baud: int, expected_test: str | None) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=False)
    rtl = out / "mutant.v"
    rtl.write_text(source)
    compile_args = ["iverilog", "-g2012", "-s", "uart_tx_apb", "-o", "preflight.vvp",
                    "-Puart_tx_apb.CLK_FREQ_HZ=1000000", f"-Puart_tx_apb.BAUD_RATE={baud}", "mutant.v"]
    compiled = command(compile_args, out, out / "compile.log")
    if compiled != 0:
        return {"classification": "invalid_compile", "killed": False, "compile_returncode": compiled}
    simulation = out / "simulation"
    args = [sys.executable, str(ROOT / "scripts/simulate.py"), "--source", str(rtl),
            "--clock", "1000000", "--baud", str(baud), "--out", str(simulation)]
    rc = command(args, ROOT, out / "simulation.log")
    result = inspect_xml(simulation / "results.xml", rc, expected_test)
    result.update({"compile_returncode": compiled, "returncode": rc, "clock_hz": 1_000_000,
                   "baud": baud, "source_sha256": sha256(rtl), "directory": str(out)})
    return result


def evaluate(out: Path) -> dict[str, Any]:
    source_path = ROOT / "rtl/uart_tx_apb.v"
    source = source_path.read_text()
    baseline = run_case(source, out / "baseline", 100_000, None)
    report: dict[str, Any] = {
        "executed_at_jst": datetime.now(ZoneInfo("Asia/Tokyo")).isoformat(),
        "source_sha256": sha256(source_path), "test_sha256": sha256(ROOT / "tests/test_uart_tx.py"),
        "driver_sha256": sha256(ROOT / "scripts/simulate.py"), "script_sha256": sha256(Path(__file__)),
        "simulator": "icarus", "baseline": baseline, "mutants": [],
        "limitation": "12 deliberate single faults; this is not exhaustive bug or mutation coverage"}
    if baseline["classification"] != "baseline_passed":
        report["status"] = "failed"
        report["reason"] = "untouched baseline must pass before evaluating mutations"
        return report
    for mutation in MUTATIONS:
        print(f"mutation: {mutation.candidate_id}", flush=True)
        changed = mutate(source, mutation)
        result = run_case(changed, out / mutation.candidate_id, mutation.baud, mutation.expected_test)
        result["mutation"] = asdict(mutation)
        report["mutants"].append(result)
    report["killed"] = sum(m["killed"] for m in report["mutants"])
    report["attempted"] = len(report["mutants"])
    report["status"] = "passed" if report["killed"] == len(MUTATIONS) else "failed"
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    try:
        report = evaluate(out)
    except Exception as error:
        report = {"status": "failed", "error": f"{type(error).__name__}: {error}"}
    (out / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"{report['status']}: {out / 'summary.json'}", flush=True)
    raise SystemExit(0 if report["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
