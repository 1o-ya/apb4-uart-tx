"""Mutation evidence must distinguish real assertion kills from infrastructure."""
from __future__ import annotations

import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from scripts.mutation_check import MUTATIONS, TEST_NAMES, inspect_xml, mutate


def xml_report(path: Path, failed: str | None = None, error_type: str = "AssertionError",
               skipped: bool = False) -> None:
    suite = ET.Element("testsuite")
    for name in TEST_NAMES:
        case = ET.SubElement(suite, "testcase", name=name)
        if name == failed:
            ET.SubElement(case, "failure", error_type=error_type, error_msg="deliberate mismatch")
        if skipped:
            ET.SubElement(case, "skipped")
    ET.ElementTree(suite).write(path)


class MutationEvidenceTests(unittest.TestCase):
    def test_anchor_must_be_unique_and_changed(self) -> None:
        mutation = MUTATIONS[0]
        self.assertEqual(mutate(mutation.before, mutation), mutation.after)
        for source in ("unrelated", mutation.before * 2):
            with self.assertRaises(ValueError):
                mutate(source, mutation)

    def test_only_expected_named_assertion_is_a_kill(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "results.xml"
            xml_report(path, TEST_NAMES[0])
            self.assertTrue(inspect_xml(path, 0, TEST_NAMES[0])["killed"])
            self.assertFalse(inspect_xml(path, 0, TEST_NAMES[1])["killed"])
            xml_report(path, TEST_NAMES[0], error_type="RuntimeError")
            self.assertFalse(inspect_xml(path, 0, TEST_NAMES[0])["killed"])

    def test_missing_empty_or_malformed_results_are_not_kills(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "results.xml"
            self.assertFalse(inspect_xml(path, 0, TEST_NAMES[0])["killed"])
            for text in ("<testsuite/>", "<broken>"):
                path.write_text(text)
                self.assertFalse(inspect_xml(path, 0, TEST_NAMES[0])["killed"])

    def test_timeout_and_skips_are_not_kills(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "results.xml"
            xml_report(path, TEST_NAMES[0])
            self.assertFalse(inspect_xml(path, 124, TEST_NAMES[0])["killed"])
            xml_report(path, TEST_NAMES[0], skipped=True)
            self.assertFalse(inspect_xml(path, 0, TEST_NAMES[0])["killed"])

    def test_successful_suite_survives(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "results.xml"
            xml_report(path)
            self.assertEqual(inspect_xml(path, 0, TEST_NAMES[0])["classification"], "survived")
            self.assertEqual(inspect_xml(path, 0, None)["classification"], "baseline_passed")
