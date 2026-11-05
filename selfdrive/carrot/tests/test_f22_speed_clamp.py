#!/usr/bin/env python3
"""
TDD Test for F-22: nRoadLimitSpeed clamping in CarrotServ.update().

RED: the `update()` JSON branch does nRoadLimitSpeed = int(json.get(...)) without a
     0~160 clamp, so out-of-range external JSON (from 7706/12345 channels) can set
     arbitrary speed limits.
GREEN: after patch, the value is clamped with np.clip(nRoadLimitSpeed, 0, 160).
"""
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
CARROT_SERV = os.path.join(ROOT, "selfdrive", "carrot", "carrot_serv.py")


class TestF22SpeedLimitClamp(unittest.TestCase):

    def _read(self):
        with open(CARROT_SERV, encoding="utf-8") as f:
          return f.read()

    def test_update_clamps_road_limit_speed(self):
        """F-22: update() MUST clamp nRoadLimitSpeed to [0, 160] like
        _handle_speed_limit_command does."""
        text = self._read()
        # The clamp call
        m = re.search(r"nRoadLimitSpeed\s*=\s*int\(json\.get\([\"']nRoadLimitSpeed[\"'].*?\)\)", text)
        self.assertIsNotNone(m, "nRoadLimitSpeed JSON assignment not found in update()")
        # A np.clip(..., 0, 160) must appear immediately after the assignment
        # Look for the F-22 marker or the clamp within 5 lines
        idx = text.find(m.group(0))
        tail = text[idx: idx + 600]
        self.assertRegex(
          tail,
          r"nRoadLimitSpeed\s*=\s*int\(np\.clip\(nRoadLimitSpeed\s*,\s*0\s*,\s*160\)\)",
          "F-22 RED: nRoadLimitSpeed is not clamped to 0~160 in update(). "
          "Apply carrot_f18_f22.patch."
        )

    def test_handle_speed_limit_already_validates(self):
        """The _handle_speed_limit_command entry already validates 0~160 (baseline
        that F-22 aligns the update() entry with)."""
        text = self._read()
        m = re.search(r"def _handle_speed_limit_command\(.*?(?=\n  def |\Z)", text, re.DOTALL)
        self.assertIsNotNone(m, "_handle_speed_limit_command not found")
        body = m.group(0)
        self.assertRegex(body, r"speed_kph\s*<\s*0\s+or\s+speed_kph\s*>\s*160",
                         "existing validator missing 0~160 range check")

if __name__ == "__main__":
    unittest.main()
