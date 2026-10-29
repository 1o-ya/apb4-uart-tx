"""The low-level simulator CLI must reject failed cocotb xUnit results too."""
from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
from scripts.simulate import simulation_passed


class SimulatorEvidenceTests(unittest.TestCase):
    def test_failed_or_skipped_demo_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "results.xml"
            for tag in ("failure", "error", "skipped"):
                path.write_text(f'<testsuite><testcase name="demo"><{tag}/></testcase></testsuite>')
                self.assertFalse(simulation_passed(path, "demo_uart_tx"))
            path.write_text('<testsuite><testcase name="demo"/></testsuite>')
            self.assertTrue(simulation_passed(path, "demo_uart_tx"))

    def test_missing_malformed_or_empty_demo_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "results.xml"
            self.assertFalse(simulation_passed(path, "demo_uart_tx"))
            for text in ('<testsuite>', '<testsuite/>'):
                path.write_text(text)
                self.assertFalse(simulation_passed(path, "demo_uart_tx"))
