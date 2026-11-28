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

    def test_vrel_guard_present_without_fatal_assert(self):
        """F-19: process_lead guards vRel convention via non-fatal check/warning instead of crashing plannerd on float jitter."""
        with open(LONG_MPC, encoding="utf-8") as f:
          text = f.read()

        m = re.search(r"def process_lead\(.*?(?=\n  def |\Z)", text, re.DOTALL)
        assert m is not None
        body = m.group(0)

        self.assertNotIn("assert v_lead >= lead.vRel - 1e-6", body,
                         "Fatal assert crashes plannerd on normal float jitter (e.g. vLead=0.05973 < vRel=0.05980)")
        self.assertIn("vRel convention violated", body)

    def test_vrel_convention_documented_in_comment(self):
        """The F-19 comment block MUST explain the convention."""
        with open(LONG_MPC, encoding="utf-8") as f:
          text = f.read()
        assert "F-19" in text, "F-19 marker comment missing in long_mpc.py"
        assert "vRel = v_lead - v_ego" in text, "vRel convention not documented in long_mpc.py"

    def test_lead_clamp_uses_correct_sign(self):
        """The lead clamp at the call site must use v_ego + vRel (not v_ego - vRel)."""
        with open(LONG_MPC, encoding="utf-8") as f:
          text = f.read()
        # The correct expression is lead_v = max(0.0, v_ego + float(radarstate.leadOne.vRel))
        assert re.search(r"lead_v\s*=\s*max\(0\.0,\s*v_ego\s*\+\s*float\(radarstate\.leadOne\.vRel\)\)", text)

if __name__ == "__main__":
    unittest.main()
