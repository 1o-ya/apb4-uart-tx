"""Run one isolated UART configuration using the pinned cocotb Python runner."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import find_libpython
from cocotb_tools import config
from cocotb_tools.runner import get_runner

ROOT = Path(__file__).resolve().parents[1]


def simulation_passed(path: Path, module: str) -> bool:
    counts = {"test_uart_tx": 8, "test_uart_stress": 1, "demo_uart_tx": 1}
    expected = sum(counts.get(name, 0) for name in module.split(","))
    try:
        cases = list(ET.parse(path).getroot().iter("testcase"))
    except (FileNotFoundError, ET.ParseError):
        return False
    names = [case.get("name") for case in cases]
    return (expected > 0 and len(cases) == expected and len(set(names)) == len(cases)
            and not any(case.find(tag) is not None for case in cases
                        for tag in ("failure", "error", "skipped")))


def launch(out: Path, clock: int, baud: int, demo: bool, sim_file: Path,
           simulator: str, module: str, seed: int) -> None:
    # cocotb 2.0.1's Icarus runner forces FST or -none. Invoke vvp explicitly
    # so dump.vcd is actual text VCD, without patching the installed library.
    env = dict(os.environ)
    libpython = find_libpython.find_libpython()
    if libpython is None:
        raise RuntimeError("Cannot locate this interpreter's libpython")
    env.update({"CLK_FREQ_HZ": str(clock), "BAUD_RATE": str(baud),
                "PYTHONPATH": str(out), "LIBPYTHON_LOC": libpython,
                "PYGPI_PYTHON_BIN": sys.executable, "TOPLEVEL_LANG": "verilog",
                "COCOTB_TOPLEVEL": "uart_tx_apb", "COCOTB_RANDOM_SEED": str(seed),
                "UART_TEST_SEED": str(seed), "COCOTB_TEST_MODULES": module,
                "COCOTB_RESULTS_FILE": str(out / "results.xml")})
    if simulator == "icarus":
        args = ["vvp", "-M", str(config.libs_dir), "-m", config.lib_name("vpi", "icarus"),
                str(sim_file), "-vcd" if demo else "-none"]
    else:
        env["COCOTB_TRUST_INERTIAL_WRITES"] = "1"
        args = [str(sim_file)] + (["--trace"] if demo else [])
    result = subprocess.run(args, cwd=out, env=env, check=False)
    valid = result.returncode == 0 and simulation_passed(out / "results.xml", module)
    raise SystemExit(0 if valid else (result.returncode or 1))


def build_and_run(args: argparse.Namespace, out: Path, build: Path) -> None:
    runner = get_runner(args.sim)
    parameters = {"CLK_FREQ_HZ": args.clock, "BAUD_RATE": args.baud}
    defines = {"UART_TX_DUMP_VCD": 1} if args.demo and args.sim == "icarus" else {}
    flags = ["-Wall"] if args.sim == "icarus" else [
        "--Wall", "-Wno-UNUSEDSIGNAL", "-Wno-WIDTHTRUNC", "-Wno-WIDTHEXPAND"]
    if args.coverage:
        if args.sim != "verilator":
            raise ValueError("HDL coverage requires Verilator")
        flags += ["--coverage"]
    source = build / "uart_tx_apb.v"
    build.mkdir(parents=True, exist_ok=True)
    shutil.copy2(args.source, source)
    runner.build(sources=[source], hdl_toplevel="uart_tx_apb",
                 parameters=parameters, defines=defines, build_args=flags,
                 always=True, waves=args.demo and args.sim == "verilator", build_dir=build)
    binary = runner.sim_file if args.sim == "icarus" else build / "uart_tx_apb"
    launch(out, args.clock, args.baud, args.demo, binary,
           args.sim, "demo_uart_tx" if args.demo else args.module, args.seed)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--clock", type=int, required=True)
    parser.add_argument("--baud", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--sim", choices=("icarus", "verilator"), default="icarus")
    parser.add_argument("--module", default="test_uart_tx")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--coverage", action="store_true")
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.xml").unlink(missing_ok=True)
    shutil.copy2(args.source, out / "source.v")
    for name in ("test_uart_tx.py", "demo_uart_tx.py", "test_uart_stress.py", "uart_stress_model.py"):
        if (ROOT / "tests" / name).is_file():
            shutil.copy2(ROOT / "tests" / name, out / name)
    if args.sim == "icarus":
        build_and_run(args, out, out / "build")
    else:
        # GNU Make/Verilator reject spaces. Temporary aliases cover both the
        # build path and cocotb's runtime files without changing the installation.
        with tempfile.TemporaryDirectory(prefix="uart-verilator-") as folder:
            temporary = Path(folder)
            alias = temporary / "cocotb"
            alias.symlink_to(config.share_dir.parent, target_is_directory=True)
            config.share_dir, config.libs_dir = alias / "share", alias / "libs"
            build_and_run(args, out, temporary / "build")


if __name__ == "__main__":
    main()
