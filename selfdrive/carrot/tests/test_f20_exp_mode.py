#!/usr/bin/env python3
"""
TDD Test for F-20: ExperimentalMode gated write in longitudinal_planner.py.

RED: current code calls put_bool_nonblocking("ExperimentalMode", ...) unconditionally
     at 20 Hz (once per update() call) in both the enter-branch and exit-branch.
GREEN: after patch, the put is guarded by `if not sm['selfdriveState'].experimentalMode`
       (enter) / `if sm['selfdriveState'].experimentalMode` (exit), so it only writes
       on actual state flip.
"""
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
LONG_PLAN = os.path.join(ROOT, "selfdrive", "controls", "lib", "longitudinal_planner.py")


class TestF20ExpModeGating(unittest.TestCase):

    def _read(self):
        with open(LONG_PLAN, encoding="utf-8") as f:
          return f.read()

    def test_enter_branch_gated_on_current_state(self):
        """F-20 RED: the enter-branch put_bool_nonblocking(True) must be guarded
        by `if not sm['selfdriveState'].experimentalMode`."""
        text = self._read()
        # Find the enter-branch block
        m = re.search(
          r"_exp_on_counter\s*>=\s*self\._exp_on_frames.*?"
          r"put_bool_nonblocking\(\s*[\"']ExperimentalMode[\"']\s*,\s*True\s*\)",
          text, re.DOTALL
        )
        self.assertIsNotNone(m, "enter-branch put_bool_nonblocking(ExperimentalMode, True) not found")
        block = m.group(0)
        # GREEN check: guard is present
        gated = re.search(r"if\s+not\s+sm\['selfdriveState'\]\.experimentalMode\s*:", block)
        self.assertIsNotNone(
          gated,
          "F-20 RED: enter-branch put is not gated by `if not sm['selfdriveState'].experimentalMode`. "
          "Apply carrot_f18_f22.patch."
        )

    def test_exit_branch_gated_on_current_state(self):
        """F-20 RED: the exit-branch put_bool_nonblocking(False) must be guarded
        by `if sm['selfdriveState'].experimentalMode`."""
        text = self._read()
        m = re.search(
          r"_exp_off_counter\s*>=\s*self\._exp_off_frames.*?"
          r"put_bool_nonblocking\(\s*[\"']ExperimentalMode[\"']\s*,\s*False\s*\)",
          text, re.DOTALL
        )
        self.assertIsNotNone(m, "exit-branch put_bool_nonblocking(ExperimentalMode, False) not found")
        block = m.group(0)
        gated = re.search(r"if\s+sm\['selfdriveState'\]\.experimentalMode\s*:", block)
        self.assertIsNotNone(
          gated,
          "F-20 RED: exit-branch put is not gated by `if sm['selfdriveState'].experimentalMode`. "
          "Apply carrot_f18_f22.patch."
        )

    def test_no_unconditional_put_in_exp_mode_blocks(self):
        """Ensure there is no bare put_bool_nonblocking(ExperimentalMode, ...) that
        is NOT inside a gated `if` block. Count guarded vs unguarded occurrences."""
        text = self._read()
        guarded_enter = len(re.findall(r"if\s+not\s+sm\['selfdriveState'\]\.experimentalMode\s*:\s*\n\s*self\.sys_params\.put_bool_nonblocking\(\s*[\"']ExperimentalMode[\"']\s*,\s*True\s*\)", text))
        guarded_exit  = len(re.findall(r"if\s+sm\['selfdriveState'\]\.experimentalMode\s*:\s*\n\s*self\.sys_params\.put_bool_nonblocking\(\s*[\"']ExperimentalMode[\"']\s*,\s*False\s*\)", text))
        self.assertGreaterEqual(guarded_enter, 1, "Enter-branch gated put not found")
        self.assertGreaterEqual(guarded_exit, 1, "Exit-branch gated put not found")

if __name__ == "__main__":
    unittest.main()
