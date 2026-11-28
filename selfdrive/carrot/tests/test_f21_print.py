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

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
CARROT_SERV = os.path.join(ROOT, "selfdrive", "carrot", "carrot_serv.py")


def read():
  with open(CARROT_SERV, encoding="utf-8") as f:
    return f.read()


class TestF21PrintToCloudlog:

  def test_cloudlog_imported(self):
    text = read()
    assert "from openpilot.common.swaglog import cloudlog" in text, "F-21 RED: cloudlog import missing."

  def test_hot_block_keep_now_uses_cloudlog(self):
    """The blind-spot keep block ('atc_bsd keep:') MUST log via cloudlog.debug."""
    text = read()
    assert 'cloudlog.debug(f"atc_bsd keep:' in text, "F-21: blind-spot keep block should use cloudlog.debug, not print()."

  def test_showdebuglog_gate_preserved(self):
    """The showDebugLog gate MUST remain (F-21 must not cancel the switch)."""
    text = read()
    assert re.search(r"if \(self\.showDebugLog & 1\) > 0:", text)

if __name__ == "__main__":
    unittest.main()
