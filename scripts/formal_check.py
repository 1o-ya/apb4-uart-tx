"""Bounded public-pin reference checks using Yosys' built-in SAT solver."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.process_guard import terminate_process_tree
SUCCESS = "SAT proof finished - no model found: SUCCESS!"
WITNESS = "SAT solving finished - model found:"
FAILURE = "Called with -verify and proof did fail!"
CONFIGS = [(10, 10), (20, 10), (25, 10)]
SHOW = ("rst_n,paddr,psel,penable,pwrite,pwdata,pstrb,pprot,"
        "prdata,pready,pslverr,tx,ref_active,ref_age,ref_frame,witness_goal")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def proof_passed(returncode: int, log: str) -> bool:
    return (returncode == 0 and SUCCESS in log and "End of script." in log
            and log.count("Import proof for assert:") >= 5
            and "Import constraint from assume cell:" in log
            and not any(s in log for s in ("ERROR:", "TIMEOUT", "FAIL!")))


def witness_found(returncode: int, log: str) -> bool:
    return (returncode == 0 and WITNESS in log and "End of script." in log
            and not any(s in log for s in ("ERROR:", "TIMEOUT")))


def run_yosys(script: str, out: Path, log_name: str) -> tuple[int, str]:
    (out / f"{log_name}.ys").write_text(script + "\n")
    with (out / f"{log_name}.log").open("w") as handle:
        proc = subprocess.Popen(["yosys", "-s", f"{log_name}.ys"], cwd=out,
                                stdout=handle, stderr=subprocess.STDOUT,
                                start_new_session=True)
        try:
            rc = proc.wait(timeout=120)
        except subprocess.TimeoutExpired:
            terminate_process_tree(proc)
            handle.write("\nTIMEOUT: killed owned Yosys process tree\n")
            rc = 124
        except KeyboardInterrupt:
            terminate_process_tree(proc)
            raise
    return rc, (out / f"{log_name}.log").read_text()


def preparation(clock: int, baud: int) -> str:
    return ("read_verilog -formal -sv -DSYNTHESIS source.v uart_tx_properties.sv; "
            f"chparam -set FORMAL_CLOCK {clock} -set FORMAL_BAUD {baud} uart_tx_properties; "
            "prep -top uart_tx_properties -flatten; async2sync; dffunmap; opt_clean; ")


def check_case(source: Path, clock: int, baud: int, out: Path,
               negative: bool = False) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=False)
    shutil.copy2(source, out / "source.v")
    harness = ROOT / "formal/uart_tx_properties.sv"
    shutil.copy2(harness, out / harness.name)
    d = (clock + baud // 2) // baud
    depth = 20 * d + 12
    script = preparation(clock, baud) + (
        f"sat -seq {depth} -set-assumes -prove-asserts -verify -timeout 60 "
        f"-dump_vcd counterexample.vcd -show {SHOW}")
    rc, log = run_yosys(script, out, "proof")
    passed = proof_passed(rc, log)
    row: dict[str, Any] = {"clock_hz": clock, "baud": baud, "divisor": d,
                           "depth_clock_steps": depth, "proof_returncode": rc,
                           "bounded_proof_passed": passed,
                           "source_sha256": sha256(out / "source.v"),
                           "harness_sha256": sha256(out / harness.name), "directory": str(out)}
    if negative:
        row["fault_detected"] = rc != 0 and rc != 124 and FAILURE in log
        row["status"] = "passed" if row["fault_detected"] else "failed"
        return row
    cover = preparation(clock, baud) + ("chformal -assert -remove; "
            f"sat -seq {depth} -set-assumes -set-at {depth} witness_goal 1 "
            f"-timeout 60 -show {SHOW} -dump_vcd reachability.vcd")
    cover_rc, cover_log = run_yosys(cover, out, "reachability")
    row["nonvacuity_witness_found"] = witness_found(cover_rc, cover_log)
    row["witness_returncode"] = cover_rc
    row["status"] = "passed" if passed and row["nonvacuity_witness_found"] else "failed"
    return row


def evaluate(out: Path) -> dict[str, Any]:
    if not shutil.which("yosys"):
        return {"status": "not_run", "reason": "yosys unavailable"}
    version = subprocess.run(["yosys", "-V"], capture_output=True, text=True,
                             timeout=10, check=False).stdout.strip()
    report: dict[str, Any] = {"status": "running", "method": "bounded SAT, no induction",
                              "yosys": version, "runner_sha256": sha256(Path(__file__)),
                              "candidates": {}}
    sources = {"control": ROOT / "rtl/uart_tx_apb.v",
               "focused": ROOT / "candidates/focused/uart_tx_apb.v"}
    for name, source in sources.items():
        print(f"formal: {name}", flush=True)
        report["candidates"][name] = [check_case(source, c, b, out / name / f"{c}_{b}")
                                         for c, b in CONFIGS]
    original = sources["control"].read_text()
    anchor = "LAST_COUNT = CLKS_PER_BIT - 1;"
    assert original.count(anchor) == 1
    mutant = out / "wrong_bit_duration.v"
    mutant.write_text(original.replace(anchor, "LAST_COUNT = CLKS_PER_BIT - 2;"))
    report["negative_control"] = check_case(mutant, 25, 10, out / "negative", negative=True)
    checks = [r["status"] == "passed" for rows in report["candidates"].values() for r in rows]
    checks.append(report["negative_control"]["status"] == "passed")
    report["status"] = "passed" if all(checks) else "failed"
    report["assumptions"] = ["initial reset asserted; discrete clock-edge reset model",
                               "legal APB setup/access and stable wait signals; read PSTRB=0",
                               "arbitrary 32-bit addresses/data and protection encodings"]
    report["limitations"] = ["bounded depth only; no unbounded proof",
                               "D=1/2/3 instances only; no proof for all parameter values",
                               "two-state symbolic model, not four-state X/Z simulation",
                               "no analog, metastability, clock-domain, or asynchronous pulse proof"]
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    try:
        report = evaluate(out)
    except Exception as exc:
        report = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
    (out / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"formal {report['status']}: {out / 'verification.json'}", flush=True)
    raise SystemExit(0 if report["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
