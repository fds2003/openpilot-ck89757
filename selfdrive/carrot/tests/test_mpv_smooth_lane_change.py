#!/usr/bin/env python3
"""
TDD Unit Test for Task 5: MPV 5.0s smooth lane change S-curve step in desire_helper.py
Verifies:
1. LANE_CHANGE_STEP_CUSTO constant exists and equals 1.2 * DT_MDL (yielding approx 4.8~5.2s transition).
2. Lane line probability decay in laneChangeStarting uses LANE_CHANGE_STEP_CUSTO.
"""
import os

C3_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))

class TestMpvSmoothLaneChange:

    def test_desire_helper_mpv_lane_change_step(self):
        dh_path = os.path.join(C3_ROOT, "selfdrive", "controls", "lib", "desire_helper.py")
        assert os.path.exists(dh_path), f"desire_helper.py missing at {dh_path}"
        with open(dh_path, "r", encoding="utf-8") as f:
            text = f.read()

        # Check for MPV smooth lane change step
        assert "LANE_CHANGE_STEP_CUSTO = 1.2 * DT_MDL" in text, "desire_helper.py MUST define LANE_CHANGE_STEP_CUSTO = 1.2 * DT_MDL for MPV 5.0s smooth transition!"
        assert "self.lane_change_ll_prob - LANE_CHANGE_STEP_CUSTO" in text, "laneChangeStarting MUST decay lane_change_ll_prob using LANE_CHANGE_STEP_CUSTO!"

if __name__ == "__main__":
    unittest.main()
