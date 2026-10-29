"""PC-only qualification for this UART: simulation, faults, bounded SAT and evidence."""
from __future__ import annotations

import argparse
import json
import platform
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.verify import (CANDIDATES, CONFIGS, command, digest, invalid_parameters,
                            junit_result, simulate, synthesize, version)
from scripts.verify import publish_demo
from scripts.mutation_check import TEST_NAMES

EXTENDED = CONFIGS + [(2_147_483_647, 2_147_483_647), (2_147_483_647, 1_073_741_824)]
SEEDS = (1, 20_261_028)
STRESS_BAUDS = (1_000_000, 400_000, 100_000)


def require_tools(full: bool) -> None:
    names = ["iverilog", "vvp", "make", "ps"]
    if full:
        names += ["verilator", "verilator_coverage", "yosys", "c++"]
    missing = [name for name in names if not shutil.which(name)]
    if missing:
        raise RuntimeError("Missing required tools: " + ", ".join(missing))


def source_manifest() -> dict[str, str]:
    paths = [*ROOT.glob("scripts/*.py"), *ROOT.glob("tests/*.py"),
             *ROOT.glob("formal/*"), *CANDIDATES.values(), ROOT / "requirements.txt",
             ROOT / "README.md", ROOT / "Makefile", ROOT / "docs/STRESS_SPEC.md"]
    return {str(p.relative_to(ROOT)): digest(p) for p in paths if p.is_file()}


def check_names(result: dict[str, Any], names: set[str]) -> dict[str, Any]:
    if set(result.get("test_names", [])) != names:
        result["passed"] = False
        result["reason"] = "unexpected_test_names"
    return result


def run_functional(source: Path, out: Path, full: bool) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    sims = ("icarus", "verilator") if full else ("icarus",)
    configs = EXTENDED if full else [(1_000_000, 1_000_000), (1_000_000, 100_000)]
    for simulator in sims:
        for clock, baud in configs:
            print(f"  {out.name} {simulator}: {clock}/{baud}", flush=True)
            row = simulate(source, clock, baud, out / simulator / f"{clock}_{baud}",
                           simulator=simulator)
            rows.append(check_names(row, set(TEST_NAMES)))
    return rows


def run_stress(source: Path, out: Path, full: bool) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    sims = ("icarus", "verilator") if full else ("icarus",)
    for simulator in sims:
        for baud in STRESS_BAUDS if full else (100_000,):
            for seed in SEEDS if full else (SEEDS[0],):
                case = out / simulator / f"1000000_{baud}_seed{seed}"
                print(f"  stress {simulator} D={(1_000_000+baud//2)//baud} seed={seed}", flush=True)
                row = simulate(source, 1_000_000, baud, case, simulator=simulator,
                               module="test_uart_stress", expected=1, seed=seed)
                check_names(row, {"test_seeded_traffic_and_independent_receiver"})
                coverage = case / "stress_coverage.json"
                row["coverage"] = json.loads(coverage.read_text()) if coverage.is_file() else None
                row["passed"] &= row["coverage"] is not None
                rows.append(row)
    return rows


def parse_lcov(path: Path) -> dict[str, Any]:
    lines: dict[int, int] = {}
    in_rtl = False
    for text in path.read_text().splitlines():
        if text.startswith("SF:"):
            in_rtl = text.endswith("uart_tx_apb.v")
        if in_rtl and text.startswith("DA:"):
            number, hits = text[3:].split(",")[:2]
            lines[int(number)] = lines.get(int(number), 0) + int(hits)
    hit = sum(value > 0 for value in lines.values())
    return {"instrumented_lines": len(lines), "hit_lines": hit,
            "line_percent": 100 * hit / len(lines) if lines else None,
            "unhit_lines": sorted(k for k, v in lines.items() if v == 0),
            "limitation": "instrumented HDL lines; not requirements or exhaustive branch coverage"}


def coverage_run(source: Path, out: Path) -> dict[str, Any]:
    row = simulate(source, 1_000_000, 100_000, out, simulator="verilator",
                   module="test_uart_tx,test_uart_stress", expected=9, seed=SEEDS[1], coverage=True)
    check_names(row, set(TEST_NAMES) | {"test_seeded_traffic_and_independent_receiver"})
    raw, info = out / "coverage.dat", out / "coverage.info"
    if not raw.is_file():
        row.update({"passed": False, "reason": "missing_hdl_coverage"})
        return row
    rc = command(["verilator_coverage", "--write-info", str(info), str(raw)],
                 out, out / "coverage-conversion.log")
    if rc != 0 or not info.is_file():
        row.update({"passed": False, "reason": "coverage_conversion_failed"})
        return row
    row["hdl_lines"] = parse_lcov(info)
    row["passed"] &= row["hdl_lines"]["instrumented_lines"] > 0
    return row


def lint(source: Path, out: Path) -> dict[str, Any]:
    out.mkdir(parents=True)
    shutil.copy2(source, out / "uart_tx_apb.v")
    waivers = ["UNUSEDSIGNAL", "WIDTHTRUNC", "WIDTHEXPAND"]
    args = ["verilator", "--lint-only", "--Wall", "-DSYNTHESIS",
            "--top-module", "uart_tx_apb", *[f"-Wno-{w}" for w in waivers], "uart_tx_apb.v"]
    rc = command(args, out, out / "lint.log")
    return {"passed": rc == 0, "returncode": rc, "waivers": waivers,
            "waiver_reason": "documented unused APB fields and bounded constant sizing; all other warnings fatal"}


def external_gate(script: str, filename: str, out: Path) -> dict[str, Any]:
    log = out.parent / f"{out.name}.log"
    rc = command([sys.executable, str(ROOT / "scripts" / script), "--out", str(out)],
                 ROOT, log, timeout_seconds=1800)
    path = out / filename
    result = json.loads(path.read_text()) if path.is_file() else {"status": "failed"}
    result["process_returncode"] = rc
    result["passed"] = rc == 0 and result.get("status") == "passed"
    return result


def candidate(name: str, source: Path, out: Path, full: bool) -> dict[str, Any]:
    print(f"candidate: {name}", flush=True)
    result: dict[str, Any] = {"source_sha256": digest(source)}
    result["functional"] = run_functional(source, out / "functional", full)
    result["stress"] = run_stress(source, out / "stress", full)
    result["demo"] = simulate(source, 1_000_000, 100_000, out / "demo", demo=True)
    checks = [*result["functional"], *result["stress"], result["demo"]]
    if full:
        result["lint"] = lint(source, out / "lint")
        result["hdl_coverage"] = coverage_run(source, out / "coverage")
        result["invalid_parameters"] = invalid_parameters(source, out / "invalid")
        result["synthesis"] = synthesize(source, out / "synthesis")
        checks += [result["lint"], result["hdl_coverage"], *result["invalid_parameters"]]
        checks += [{"passed": result["synthesis"]["status"] == "passed"}]
    result["passed"] = all(row["passed"] for row in checks)
    return result


def evaluate(out: Path, full: bool) -> dict[str, Any]:
    import cocotb
    require_tools(full)
    manifest = source_manifest()
    result: dict[str, Any] = {
        "status": "running", "profile": "full" if full else "quick",
        "started_at_jst": datetime.now(ZoneInfo("Asia/Tokyo")).isoformat(),
        "platform": platform.platform(), "python": sys.version, "cocotb": cocotb.__version__,
        "iverilog": version(["iverilog", "-V"]),
        "verilator": version(["verilator", "--version"]), "yosys": version(["yosys", "-V"]),
        "manifest_sha256": manifest, "candidates": {}, "hardware": "not_run",
        "external_third_party_reproduction": "unknown", "github_ci": "not_run"}
    for name, source in CANDIDATES.items():
        result["candidates"][name] = candidate(name, source, out / name, full)
    result["evidence_unit_tests"] = external_gate("unit_check.py", "verification.json", out / "unit")
    checks = [row["passed"] for row in result["candidates"].values()]
    checks.append(result["evidence_unit_tests"]["passed"])
    if full:
        result["mutations"] = external_gate("mutation_check.py", "summary.json", out / "mutations")
        result["formal"] = external_gate("formal_check.py", "verification.json", out / "formal")
        checks += [result["mutations"]["passed"], result["formal"]["passed"]]
    result["source_unchanged_during_run"] = manifest == source_manifest()
    checks.append(result["source_unchanged_during_run"])
    result["status"] = "passed" if all(checks) else "failed"
    result["finished_at_jst"] = datetime.now(ZoneInfo("Asia/Tokyo")).isoformat()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("quick", "full"), default="full")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    stamp = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y%m%dT%H%M%S%f")
    out = (args.out or ROOT / "reports/runs" / f"qualification-{stamp}").resolve()
    out.mkdir(parents=True, exist_ok=False)
    latest = ROOT / "reports/latest-qualification.json"
    latest.write_text(json.dumps({"status": "running", "run": str(out)}))
    try:
        result = evaluate(out, args.profile == "full")
    except KeyboardInterrupt:
        result = {"status": "cancelled", "reason": "user_interrupted"}
    except Exception as exc:
        result = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
    result["run"] = str(out.relative_to(ROOT))
    text = json.dumps(result, indent=2) + "\n"
    (out / "verification.json").write_text(text)
    latest.write_text(text)
    if result["status"] == "passed":
        publish_demo(result)
    print(f"{result['status']}: {out / 'verification.json'}", flush=True)
    raise SystemExit(0 if result["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
