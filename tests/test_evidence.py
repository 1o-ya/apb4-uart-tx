"""Evidence must fail closed when simulator output is absent or incomplete."""
from __future__ import annotations

import tempfile
import unittest
import subprocess
import sys
from pathlib import Path
from scripts.verify import command, junit_result, valid_vcd


class EvidenceTests(unittest.TestCase):
    def test_missing_output_is_not_a_pass(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            self.assertFalse(junit_result(Path(folder) / "missing.xml", 8)["passed"])
            path = Path(folder) / "empty.xml"
            path.write_text('<testsuite/>')
            self.assertFalse(junit_result(path, 1)["passed"])

    def test_incomplete_or_skipped_suite_is_not_a_pass(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "results.xml"
            path.write_text('<testsuite><testcase name="a"/></testsuite>')
            self.assertFalse(junit_result(path, 8)["passed"])
            path.write_text('<testsuite><testcase name="a"><skipped/></testcase></testsuite>')
            self.assertFalse(junit_result(path, 1)["passed"])

    def test_failure_is_not_a_pass(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "results.xml"
            path.write_text('<testsuite><testcase name="a"><failure/></testcase></testsuite>')
            self.assertFalse(junit_result(path, 1)["passed"])
            path.write_text('<testsuite><testcase name="a"/></testsuite>')
            self.assertTrue(junit_result(path, 1)["passed"])

    def test_malformed_duplicate_or_wrong_names_are_not_a_pass(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "results.xml"
            path.write_text('<testsuite>')
            self.assertFalse(junit_result(path, 1)["passed"])
            path.write_text('<testsuite><testcase name="a"/><testcase name="a"/></testsuite>')
            self.assertFalse(junit_result(path, 2)["passed"])
            path.write_text('<testsuite><testcase name="b"/></testsuite>')
            self.assertFalse(junit_result(path, 1, {"a"})["passed"])

    def test_binary_or_missing_waveform_is_not_vcd(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "dump.vcd"
            self.assertFalse(valid_vcd(path))
            path.write_bytes(b"\x00\x80fake-fst")
            self.assertFalse(valid_vcd(path))
            path.write_text('$timescale 1ps $end\n$var wire 1 ! tx $end\n'
                            '$enddefinitions $end\n#0\n1!\n')
            self.assertTrue(valid_vcd(path))

    def test_timeout_stops_simulator_child(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            body = ("import pathlib,subprocess,sys,time; "
                    "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); "
                    "pathlib.Path('child.pid').write_text(str(p.pid)); time.sleep(30)")
            rc = command([sys.executable, "-c", body], out, out / "log", timeout_seconds=1)
            self.assertEqual(rc, 124)
            pid = (out / "child.pid").read_text()
            state = subprocess.run(["ps", "-o", "stat=", "-p", pid],
                                   capture_output=True, text=True, check=False).stdout.strip()
            self.assertTrue(not state or state.startswith("Z"), state)
