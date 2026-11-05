#!/usr/bin/env python3
"""
TDD tests for OP-01 (radar overpass filter) and OP-06 (longitudinal stopping).

These tests assert the POST-FIX state (defects corrected).
They are GREEN after the OP patches land; they FAIL on a clean tree.
"""
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
RADARD = os.path.join(ROOT, "selfdrive", "controls", "radard.py")
LONCTRL = os.path.join(ROOT, "selfdrive", "controls", "lib", "longcontrol.py")


def _read(path):
  with open(path, encoding="utf-8") as f:
    return f.read()


class TestOP01OverpassFilter(unittest.TestCase):
  """OP-01: unified _should_filter_lead() + position-keyed overpass tracker."""

  def test_unified_filter_entry_present(self):
    """Post-fix: a single _should_filter_lead() entry point exists."""
    text = _read(RADARD)
    self.assertRegex(text, r"def _should_filter_lead\(",
                     "OP-01 GREEN: unified _should_filter_lead() expected")

  def test_tracker_keyed_by_position_not_slot(self):
    """Post-fix: tracker keyed by a stable (dRel, yRel) position, not raw tid slot."""
    text = _read(RADARD)
    self.assertIn("_lead_position_key", text,
                  "OP-01 GREEN: position-key helper expected")
    self.assertRegex(text, r"self\._overpass_tracker\[key\]\s*=",
                     "OP-01 GREEN: tracker keyed by position key expected")

  def test_legacy_track_filter_delegates(self):
    """Post-fix: _is_overpass(Track) delegates to the unified entry point."""
    text = _read(RADARD)
    m = re.search(r"def _is_overpass\(self, track\)[^:]*:.*?return self\._should_filter_lead\(track\)",
                  text, re.DOTALL)
    self.assertIsNotNone(m, "OP-01 GREEN: _is_overpass should delegate to _should_filter_lead")


class TestOP06StoppingBranchDecay(unittest.TestCase):
  """OP-06: stopping branch uses jerk-limited transition to a closed-form target."""

  def test_stopping_branch_no_multiplicative_feedback(self):
    """Post-fix: output_accel no longer seeds directly from last_output_accel
    in the stopping branch; instead a jerk limit is applied to a target."""
    text = _read(LONCTRL)
    # The pre-fix bug pattern is gone
    self.assertNotRegex(text,
      r"output_accel\s*=\s*self\.last_output_accel\s*\n\s*\n\s*if soft_hold",
      "OP-06 GREEN: raw last_output_accel seed should be replaced by jerk-limited transition")

  def test_jerk_limit_in_stopping_branch(self):
    """Post-fix: a per-frame jerk limit constant exists in the stopping branch."""
    text = _read(LONCTRL)
    self.assertIn("_J_STOP", text, "OP-06 GREEN: jerk-limit constant expected")

  def test_stopping_decrements_with_jerk(self):
    """Post-fix: the stopping branch clamps output_accel toward stopAccel by _J_STOP."""
    text = _read(LONCTRL)
    m = re.search(r"output_accel\s*=\s*max\(stopAccel,\s*self\.last_output_accel\s*-\s*_J_STOP\)", text)
    self.assertIsNotNone(m, "OP-06 GREEN: jerk-limited downward step expected")


if __name__ == "__main__":
  unittest.main()
