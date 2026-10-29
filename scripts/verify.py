"""A bounded two-candidate APB UART experiment; no model API or generic harness."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.process_guard import terminate_process_tree
CONFIGS = [(1_000_000, b) for b in (1_000_000, 500_000, 400_000,
                                  300_000, 125_000, 100_000)] + [(50_000_000, 115_200)]
INVALID = [(0, 1), (-1, 1), (1_000_000, 0), (1_000_000, -1), (1, 2)]
CANDIDATES = {"control": ROOT / "rtl/uart_tx_apb.v",
              "focused": ROOT / "candidates/focused/uart_tx_apb.v"}
DIAGNOSTIC = "Require CLK_FREQ_HZ > 0 and 0 < BAUD_RATE <= CLK_FREQ_HZ"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def junit_result(path: Path, expected: int,
                 expected_names: set[str] | None = None) -> dict[str, Any]:
    if not path.is_file():
        return {"passed": False, "reason": "missing_results"}
    try:
        cases = list(ET.parse(path).getroot().iter("testcase"))
    except ET.ParseError:
        return {"passed": False, "reason": "malformed_results"}
    names = [str(c.get("name")) for c in cases]
    failures = [c.get("name") for c in cases
                if any(c.find(tag) is not None for tag in ("failure", "error", "skipped"))]
    correct_names = expected_names is None or set(names) == expected_names
    return {"passed": len(cases) == expected and len(set(names)) == len(names)
            and correct_names and not failures,
            "tests": len(cases), "failures": failures, "test_names": names}


def command(args: list[str], cwd: Path, log: Path,
            timeout_seconds: float = 180) -> int:
    env = dict(os.environ)
    for key in list(env):
        if key.startswith(("COCOTB_", "GPI_", "PYGPI_")) or key in (
                "PYTHONPATH", "PYTHONHOME", "RANDOM_SEED", "WAVES", "LIBPYTHON_LOC"):
            env.pop(key)
    try:
        with log.open("w") as handle:
            proc = subprocess.Popen(args, cwd=cwd, env=env, stdout=handle,
                                    stderr=subprocess.STDOUT, start_new_session=True)
            try:
                return proc.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                terminate_process_tree(proc)
                raise
            except KeyboardInterrupt:
                terminate_process_tree(proc)
                raise
    except subprocess.TimeoutExpired:
        with log.open("a") as handle:
            handle.write(f"\nTIMEOUT after {timeout_seconds} seconds; owned process tree killed\n")
        return 124


def valid_vcd(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        text = path.read_text(encoding="ascii")
    except UnicodeDecodeError:
        return False
    return (all(token in text for token in ("$timescale", "$var", "$enddefinitions"))
            and re.search(r"(?m)^#\d+$", text) is not None)


def simulate(source: Path, clock: int, baud: int, out: Path,
             demo: bool = False, simulator: str = "icarus", module: str = "test_uart_tx",
             expected: int = 8, seed: int = 0, coverage: bool = False) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=False)
    args = [sys.executable, str(ROOT / "scripts/simulate.py"), "--source", str(source),
            "--clock", str(clock), "--baud", str(baud), "--out", str(out),
            "--sim", simulator, "--module", module, "--seed", str(seed)]
    extras = (["--demo"] if demo else []) + (["--coverage"] if coverage else [])
    rc = command(args + extras, ROOT, out / "simulation.log", timeout_seconds=300)
    result = junit_result(out / "results.xml", 1 if demo else expected)
    result.update({"returncode": rc, "clock_hz": clock, "baud": baud,
                   "divisor": (clock + baud // 2) // baud,
                   "directory": str(out.relative_to(ROOT)), "source_sha256": digest(source),
                   "simulator": simulator, "module": module, "seed": seed})
    result["passed"] = result["passed"] and rc == 0
    runtime = re.search(r"Runtime Python version: (\S+)", (out / "simulation.log").read_text())
    result["embedded_python"] = runtime.group(1) if runtime else "unavailable"
    if demo:
        wave = out / "dump.vcd"
        result["waveform_bytes"] = wave.stat().st_size if wave.is_file() else 0
        result["valid_text_vcd"] = valid_vcd(wave)
        result["passed"] = result["passed"] and result["valid_text_vcd"]
    return result


def invalid_parameters(source: Path, out: Path) -> list[dict[str, Any]]:
    out.mkdir(parents=True)
    shutil.copy2(source, out / "source.v")
    results: list[dict[str, Any]] = []
    for index, (clock, baud) in enumerate(INVALID):
        args = ["iverilog", "-g2012", "-s", "uart_tx_apb", "-o", f"bad{index}.vvp",
                f"-Puart_tx_apb.CLK_FREQ_HZ={clock}",
                f"-Puart_tx_apb.BAUD_RATE={baud}", "source.v"]
        compiled = command(args, out, out / f"{index}-compile.log")
        rc = command(["vvp", f"bad{index}.vvp"], out, out / f"{index}-run.log") if compiled == 0 else 0
        text = (out / f"{index}-run.log").read_text() if compiled == 0 else ""
        results.append({"clock_hz": clock, "baud": baud, "returncode": rc,
                        "passed": compiled == 0 and rc not in (0, 124) and DIAGNOSTIC in text})
    return results


def synthesize(source: Path, out: Path) -> dict[str, Any]:
    if not shutil.which("yosys"):
        return {"status": "not_run", "reason": "yosys_unavailable"}
    out.mkdir(parents=True)
    shutil.copy2(source, out / "source.v")
    script = ("read_verilog -DSYNTHESIS source.v; hierarchy -check -top uart_tx_apb; "
              "synth -top uart_tx_apb; check -assert; tee -o stats.json stat -json")
    rc = command(["yosys", "-p", script], out, out / "yosys.log")
    result: dict[str, Any] = {"status": "passed" if rc == 0 else "failed",
                              "parameters": {"clock_hz": 50_000_000, "baud": 115_200},
                              "target": "Yosys generic cells; no PDK/FPGA mapping"}
    if rc == 0:
        stats = json.loads((out / "stats.json").read_text())
        module = stats["modules"]["\\uart_tx_apb"]
        result.update({"generic_cells": module["num_cells"],
                       "cell_types": module["num_cells_by_type"]})
    return result


def mutation_check(out: Path) -> dict[str, Any]:
    source = out / "mutation.v"
    original = CANDIDATES["control"].read_text()
    before = "LAST_COUNT = CLKS_PER_BIT - 1;"
    assert original.count(before) == 1
    source.write_text(original.replace(before, "LAST_COUNT = CLKS_PER_BIT - 2;"))
    result = simulate(source, 1_000_000, 100_000, out / "simulation", demo=True)
    failure_text = (out / "simulation/results.xml").read_text()
    detected = (result.get("tests") == 1 and bool(result.get("failures"))
                and result["returncode"] != 124 and "tx=" in failure_text
                and "expected=" in failure_text)
    return {"passed": detected, "purpose": "deliberate negative control, not a generated candidate",
            "fault": "bit duration D-1 instead of D", "simulation": result}


def version(args: list[str]) -> str:
    if not shutil.which(args[0]):
        return "unavailable"
    result = subprocess.run(args, capture_output=True, text=True, timeout=15, check=False)
    return (result.stdout or result.stderr).splitlines()[0]


def publish_demo(report: dict[str, Any]) -> None:
    demo = report["candidates"]["control"]["demo"]
    if not demo["passed"]:
        return
    source = ROOT / demo["directory"]
    target = ROOT / "reports/demo"
    target.mkdir(parents=True, exist_ok=True)
    for name in ("dump.vcd", "results.xml", "simulation.log"):
        shutil.copy2(source / name, target / name)
    (target / "verification.json").write_text(json.dumps(demo, indent=2) + "\n")
    print(f"Waveform: {target / 'dump.vcd'}", flush=True)


def evaluate_candidate(name: str, source: Path, run: Path, demo_only: bool) -> dict[str, Any]:
    base = run / name
    print(f"{name}: demo and fixed regression configurations", flush=True)
    demo = simulate(source, 1_000_000, 100_000, base / "demo", demo=True)
    result: dict[str, Any] = {"source_sha256": digest(source), "demo": demo}
    if not demo_only:
        result["matrix"] = [simulate(source, clk, baud, base / f"{clk}_{baud}")
                            for clk, baud in CONFIGS]
        result["invalid_parameters"] = invalid_parameters(source, base / "invalid")
        result["generic_synthesis"] = synthesize(source, base / "synthesis")
    checks = [demo] + result.get("matrix", []) + result.get("invalid_parameters", [])
    result["passed"] = all(c["passed"] for c in checks)
    result["passed"] &= result.get("generic_synthesis", {}).get("status") != "failed"
    return result


def evaluate(run: Path, demo_only: bool) -> dict[str, Any]:
    import cocotb
    report: dict[str, Any] = {
        "status": "running", "scope": "demo_only" if demo_only else "full",
        "executed_at": datetime.now(ZoneInfo("Asia/Tokyo")).isoformat(),
        "python": sys.version.split()[0], "cocotb": cocotb.__version__,
        "iverilog": version(["iverilog", "-V"]), "yosys": version(["yosys", "-V"]),
        "test_sha256": digest(ROOT / "tests/test_uart_tx.py"), "cocotb_prng_seed": 0,
        "demo_sha256": digest(ROOT / "tests/demo_uart_tx.py"),
        "runner_sha256": digest(Path(__file__)),
        "simulator_driver_sha256": digest(ROOT / "scripts/simulate.py"),
        "candidates": {}, "hardware": "not_run", "formal": "not_run",
        "third_party_reproduction": "unknown", "demand": "unknown", "revenue": "unknown"}
    for name, source in CANDIDATES.items():
        report["candidates"][name] = evaluate_candidate(name, source, run, demo_only)
    checks = [c["passed"] for c in report["candidates"].values()]
    if not demo_only:
        report["negative_control"] = mutation_check(run)
        checks.append(report["negative_control"]["passed"])
        rc = command([sys.executable, str(ROOT / "scripts/unit_check.py"), "--out", str(run / "unit")],
                     ROOT, run / "unit-gate.log")
        unit = json.loads((run / "unit/verification.json").read_text())
        report["evidence_unit_tests"] = {**unit, "passed": rc == 0 and unit["status"] == "passed"}
        checks.append(report["evidence_unit_tests"]["passed"])
    report["status"] = "passed" if all(checks) else "failed"
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo-only", action="store_true")
    args = parser.parse_args()
    stamp = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y%m%dT%H%M%S%f")
    run = ROOT / "reports/runs" / stamp
    run.mkdir(parents=True, exist_ok=False)
    latest = ROOT / "reports/latest.json"
    latest.write_text(json.dumps({"status": "running", "run": str(run.relative_to(ROOT))}))
    try:
        report = evaluate(run, args.demo_only)
    except KeyboardInterrupt:
        report = {"status": "cancelled", "reason": "user_interrupted"}
    except Exception as exc:
        report = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
    report["run"] = str(run.relative_to(ROOT))
    text = json.dumps(report, indent=2) + "\n"
    (run / "verification.json").write_text(text)
    latest.write_text(text)
    if report["status"] == "passed":
        publish_demo(report)
    print(f"{report['status']}: {run / 'verification.json'}", flush=True)
    raise SystemExit(0 if report["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
