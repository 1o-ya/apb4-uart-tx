"""Coverage and required-test identities must not be inferred from process success."""
from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
from scripts.qualify import check_names, parse_lcov


class QualificationEvidenceTests(unittest.TestCase):
    def test_unexpected_named_suite_is_rejected(self) -> None:
        result = {"passed": True, "test_names": ["other"]}
        self.assertFalse(check_names(result, {"required"})["passed"])
        result = {"passed": False, "test_names": ["required"]}
        self.assertFalse(check_names(result, {"required"})["passed"])

    def test_hdl_line_metrics_exclude_cpp_and_keep_unhit_lines(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "coverage.info"
            path.write_text('SF:/tmp/uart_tx_apb.v\nDA:4,2\nDA:5,0\nend_of_record\n'
                            'SF:/tmp/verilator.cpp\nDA:1,999\nend_of_record\n')
            result = parse_lcov(path)
            self.assertEqual(result["instrumented_lines"], 2)
            self.assertEqual(result["hit_lines"], 1)
            self.assertEqual(result["unhit_lines"], [5])
            self.assertEqual(result["line_percent"], 50)
