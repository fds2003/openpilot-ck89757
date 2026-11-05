#!/usr/bin/env python3
"""
TDD Test for F-21 (SPEC-conformed): hot-path print() -> cloudlog.debug in
carrot_serv.py.

Scope (per plan document SS2.13):
  - Only the HOT PATH (update_auto_turn blind-spot block) is converted to
    cloudlog.debug. Non-hot-path prints are out of scope and stay as print().
  - The showDebugLog-gated print MUST keep its gate (switch preserved); only
    the sink changes from print to cloudlog.debug.

RED: hot block still uses print(), or the showDebugLog gate was removed.
GREEN: hot block logs via cloudlog.debug AND the showDebugLog gate is intact.
"""
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
CARROT_SERV = os.path.join(ROOT, "selfdrive", "carrot", "carrot_serv.py")


def read():
  with open(CARROT_SERV, encoding="utf-8") as f:
    return f.read()


class TestF21PrintToCloudlog(unittest.TestCase):

  def test_cloudlog_imported(self):
    text = read()
    self.assertIn(
      "from openpilot.common.swaglog import cloudlog", text,
      "F-21 RED: cloudlog import missing."
    )

  def test_hot_block_keep_now_uses_cloudlog(self):
    """The blind-spot keep block ('atc_bsd keep:') MUST log via cloudlog.debug."""
    text = read()
    self.assertIn(
      'cloudlog.debug(f"atc_bsd keep:', text,
      "F-21: blind-spot keep block should use cloudlog.debug, not print()."
    )

  def test_showdebuglog_gate_preserved(self):
    """The showDebugLog gate MUST remain (F-21 must not cancel the switch)."""
    text = read()
    self.assertRegex(
      text, r"if \(self\.showDebugLog & 1\) > 0:",
      "F-21 RED: showDebugLog gate was removed/corrupted. Gate must stay."
    )

if __name__ == "__main__":
    unittest.main()
