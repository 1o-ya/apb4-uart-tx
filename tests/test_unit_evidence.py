"""Pure verdict checks; these do not recursively discover or execute test suites."""
from __future__ import annotations

import unittest

from scripts.unit_check import pass_decision, suite_ids


class UnitEvidenceTests(unittest.TestCase):
    def test_exact_nonempty_manifest_passes(self) -> None:
        result = pass_decision(["suite.a", "suite.b"], ["suite.a", "suite.b"], 2)
        self.assertEqual(result["status"], "passed")

    def test_empty_discovery_fails(self) -> None:
        self.assertEqual(pass_decision([], [], 0)["status"], "failed")

    def test_wrong_named_or_incomplete_execution_fails(self) -> None:
        for expected, executed, count in ((["a"], ["b"], 1), (["a", "b"], ["a"], 1),
                                           (["a"], ["a"], 0), (["a"], ["a", "b"], 2)):
            with self.subTest(expected=expected, executed=executed, count=count):
                self.assertEqual(pass_decision(expected, executed, count)["status"], "failed")

    def test_duplicate_ids_fail(self) -> None:
        self.assertEqual(pass_decision(["a", "a"], ["a", "a"], 2)["status"], "failed")

    def test_skips_errors_failures_and_stop_fail(self) -> None:
        for field in ("failures", "errors", "skipped", "expected_failures", "unexpected_successes"):
            with self.subTest(field=field):
                self.assertEqual(pass_decision(["a"], ["a"], 1, **{field: 1})["status"], "failed")
        self.assertEqual(pass_decision(["a"], ["a"], 1, stopped=True)["status"], "failed")

    def test_nested_suite_ids_are_collected_before_execution(self) -> None:
        first = UnitEvidenceTests("test_empty_discovery_fails")
        second = UnitEvidenceTests("test_duplicate_ids_fail")
        suite = unittest.TestSuite([unittest.TestSuite([first]), second])
        self.assertEqual(suite_ids(suite), [first.id(), second.id()])
