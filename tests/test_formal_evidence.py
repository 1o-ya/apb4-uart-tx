"""Missing, truncated, timeout, and failed solver logs must not become passes."""
from __future__ import annotations

import unittest
from scripts.formal_check import SUCCESS, WITNESS, proof_passed, witness_found

COMPLETE = ("Import proof for assert:\n" * 5 +
            "Import constraint from assume cell:\n" + SUCCESS + "\nEnd of script.")


class FormalEvidenceTests(unittest.TestCase):
    def test_success_requires_complete_log_and_zero_returncode(self) -> None:
        self.assertTrue(proof_passed(0, COMPLETE))
        self.assertFalse(proof_passed(1, COMPLETE))
        self.assertFalse(proof_passed(0, SUCCESS))
        self.assertFalse(proof_passed(0, ""))
        self.assertFalse(proof_passed(0, SUCCESS + "\nEnd of script."))

    def test_error_timeout_or_failed_proof_cannot_pass(self) -> None:
        for marker in ("ERROR:", "TIMEOUT", "FAIL!"):
            self.assertFalse(proof_passed(0, COMPLETE + "\n" + marker))

    def test_reachability_needs_a_model(self) -> None:
        self.assertTrue(witness_found(0, WITNESS + "\nEnd of script."))
        self.assertFalse(witness_found(0, "no model found\nEnd of script."))
        self.assertFalse(witness_found(1, WITNESS + "\nEnd of script."))
        self.assertFalse(witness_found(0, WITNESS + "\nEnd of script.\nTIMEOUT"))
