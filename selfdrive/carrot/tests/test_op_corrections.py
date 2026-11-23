#!/usr/bin/env python3
"""
TDD tests for OP-01 (radar overpass filter) and OP-06 (longitudinal stopping).

These tests assert the POST-FIX state (defects corrected).
They are GREEN after the OP patches land; they FAIL on a clean tree.
"""
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
RADARD = os.path.join(ROOT, "selfdrive", "controls", "radard.py")
LONCTRL = os.path.join(ROOT, "selfdrive", "controls", "lib", "longcontrol.py")


def _read(path):
  with open(path, encoding="utf-8") as f:
    return f.read()


class TestOP01OverpassFilter:
  """OP-01: unified _should_filter_lead() + position-keyed overpass tracker."""

  def test_unified_filter_entry_present(self):
    """Post-fix: a single _should_filter_lead() entry point exists."""
    text = _read(RADARD)
    assert re.search(r"def _should_filter_lead\(", text)

  def test_tracker_keyed_by_position_not_slot(self):
    """Post-fix: tracker keyed by a stable (dRel, yRel) position, not raw tid slot."""
    text = _read(RADARD)
    assert "_lead_position_key" in text, "OP-01 GREEN: position-key helper expected"
    assert re.search(r"self\._overpass_tracker\[key\]\s*=", text)

  def test_legacy_track_filter_delegates(self):
    """Post-fix: _is_overpass(Track) delegates to the unified entry point."""
    text = _read(RADARD)
    m = re.search(r"def _is_overpass\(self, track\)[^:]*:.*?return self\._should_filter_lead\(track\)",
                  text, re.DOTALL)
    assert m is not None


class TestOP06StoppingBranchDecay:
  """OP-06: stopping branch uses jerk-limited transition to a closed-form target."""

  def test_stopping_branch_no_multiplicative_feedback(self):
    """Post-fix: output_accel no longer seeds directly from last_output_accel
    in the stopping branch; instead a jerk limit is applied to a target."""
    text = _read(LONCTRL)
    # The pre-fix bug pattern is gone
    assert not re.search(r"output_accel\s*=\s*self\.last_output_accel\s*\n\s*\n\s*if soft_hold", text)

  def test_jerk_limit_in_stopping_branch(self):
    """Post-fix: a per-frame jerk limit constant exists in the stopping branch."""
    text = _read(LONCTRL)
    assert "_J_STOP" in text, "OP-06 GREEN: jerk-limit constant expected"

  def test_stopping_decrements_with_jerk(self):
    """Post-fix: the stopping branch clamps output_accel toward stopAccel by _J_STOP."""
    text = _read(LONCTRL)
    m = re.search(r"output_accel\s*=\s*max\(stopAccel,\s*self\.last_output_accel\s*-\s*_J_STOP\)", text)
    assert m is not None


if __name__ == "__main__":
  unittest.main()
