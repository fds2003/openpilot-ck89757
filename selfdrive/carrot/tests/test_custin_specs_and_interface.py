#!/usr/bin/env python3
"""
TDD Unit Test for Task 1 & Task 2:
1. HYUNDAI_CUSTIN_1ST_GEN specs in values.py (mass=1754, flags |= SEND_LFA).
2. Dedicated CUSTIN override in interface.py (steerActuatorDelay=0.15, startAccel=1.0).
"""
import os
import re
import unittest

C3_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))

class TestCustinSpecsAndInterface(unittest.TestCase):

    def test_values_mass_and_send_lfa(self):
        """Task 1: Verify values.py sets mass=1754 and binds HyundaiFlags.SEND_LFA"""
        values_path = os.path.join(C3_ROOT, "opendbc_repo", "opendbc", "car", "hyundai", "values.py")
        self.assertTrue(os.path.exists(values_path), f"values.py missing at {values_path}")
        with open(values_path, "r", encoding="utf-8") as f:
            text = f.read()

        start_idx = text.find("HYUNDAI_CUSTIN_1ST_GEN")
        self.assertNotEqual(start_idx, -1, "Could not find HYUNDAI_CUSTIN_1ST_GEN in values.py")
        end_idx = text.find("HYUNDAI_CASPER", start_idx)
        block = text[start_idx:end_idx]

        # Check mass == 1754
        self.assertIn("mass=1754", block, "HYUNDAI_CUSTIN_1ST_GEN mass MUST be 1754 kg for 2.0T Flagship!")
        # Check SEND_LFA flag
        self.assertIn("HyundaiFlags.SEND_LFA", block, "HYUNDAI_CUSTIN_1ST_GEN flags MUST include SEND_LFA!")

    def test_interface_dedicated_custin_override(self):
        """Task 2: Verify interface.py has dedicated HYUNDAI_CUSTIN_1ST_GEN override"""
        interface_path = os.path.join(C3_ROOT, "opendbc_repo", "opendbc", "car", "hyundai", "interface.py")
        self.assertTrue(os.path.exists(interface_path), f"interface.py missing at {interface_path}")
        with open(interface_path, "r", encoding="utf-8") as f:
            text = f.read()

        # Check for dedicated branch
        self.assertIn("candidate == CAR.HYUNDAI_CUSTIN_1ST_GEN", text,
                      "interface.py MUST contain explicit candidate == CAR.HYUNDAI_CUSTIN_1ST_GEN override branch!")
        self.assertIn("ret.steerActuatorDelay = 0.15", text,
                      "Custin 2.0T MUST set steerActuatorDelay = 0.15 for 3.055m wheelbase lead lag!")

if __name__ == "__main__":
    unittest.main()
