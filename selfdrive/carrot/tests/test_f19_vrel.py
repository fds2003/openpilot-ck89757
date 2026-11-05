#!/usr/bin/env python3
"""
TDD Test for F-19: vRel sign convention lock.

Verifies that long_mpc.py contains the assertion guarding vLead >= vRel - 1e-6.
RED: assertion not present (current code has no guard).
GREEN: assertion present after applying carrot_f18_f22.patch.
"""
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
LONG_MPC = os.path.join(ROOT, "selfdrive", "controls", "lib", "longitudinal_mpc_lib", "long_mpc.py")


class TestF19VRelConvention(unittest.TestCase):

    def test_vrel_assertion_present_in_process_lead(self):
        """F-19: process_lead MUST contain an assert that vLead >= vRel - 1e-6
        to lock the cross-file sign convention vRel = v_lead - v_ego."""
        with open(LONG_MPC, encoding="utf-8") as f:
          text = f.read()

        m = re.search(r"def process_lead\(.*?(?=\n  def |\Z)", text, re.DOTALL)
        self.assertIsNotNone(m, "process_lead not found in long_mpc.py")
        body = m.group(0)

        # Look for the F-19 guard assertion
        guard = re.search(r"assert\s+v_lead\s*>=\s*lead\.vRel\s*-\s*1e-6", body)
        self.assertIsNotNone(
          guard,
          "F-19 RED: vRel sign convention assert missing in process_lead. "
          "Apply carrot_f18_f22.patch to add it."
        )

    def test_vrel_convention_documented_in_comment(self):
        """The F-19 comment block MUST explain the convention."""
        with open(LONG_MPC, encoding="utf-8") as f:
          text = f.read()
        self.assertIn("F-19", text, "F-19 marker comment missing in long_mpc.py")
        self.assertIn("vRel = v_lead - v_ego", text,
          "vRel convention not documented in long_mpc.py")

    def test_lead_clamp_uses_correct_sign(self):
        """The lead clamp at the call site must use v_ego + vRel (not v_ego - vRel)."""
        with open(LONG_MPC, encoding="utf-8") as f:
          text = f.read()
        # The correct expression is lead_v = max(0.0, v_ego + float(radarstate.leadOne.vRel))
        self.assertRegex(
          text,
          r"lead_v\s*=\s*max\(0\.0,\s*v_ego\s*\+\s*float\(radarstate\.leadOne\.vRel\)\)",
          "lead_v MUST be v_ego + vRel (not minus)."
        )

if __name__ == "__main__":
    unittest.main()
