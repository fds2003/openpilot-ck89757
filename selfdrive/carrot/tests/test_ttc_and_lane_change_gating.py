#!/usr/bin/env python3
"""
TDD Unit Test for Slice 1: TTC Calculation and Lane Change Gating (F-32-01)
Verifies:
1. Empty lane (no approaching vehicle) MUST permit lane change (rear_conflict == False).
2. Fast approaching vehicle (TTC < threshold) MUST block lane change (rear_conflict == True).
3. 3-level overtake thresholds (Aggressive 1.8s / Normal 2.5s / Safe 3.5s).
4. Sensor offline / invalid data MUST fail-safe block (rear_conflict == True).
"""
import unittest

def calculate_rear_ttc(main_lb_drel, lb_vrel, main_rb_drel, rb_vrel, sensor_alive=True):
    """
    Computes rear TTC:
    - If sensors are alive, but no targets are approaching (ttc_list is empty): returns 99.0 (clear/safe).
    - If approaching vehicle exists: returns min(TTC).
    - If sensors are offline/dead: returns 0.0 (fail-safe unknown).
    """
    if not sensor_alive:
        return 0.0

    ttc_list = []
    for d, v in [(main_lb_drel, lb_vrel), (main_rb_drel, rb_vrel)]:
        if d is not None and abs(d) > 0 and v is not None and v < -0.1:
            ttc_list.append((abs(d) / 1000.0) / abs(v))

    return min(ttc_list) if ttc_list else 99.0

def evaluate_rear_conflict(behind_ttc, overtake_mode, amap_alive=True):
    """
    Evaluates whether rear traffic conflicts with lane change:
    - behind_ttc == 99.0: clear lane -> False (no conflict, permit)
    - 0.0 < behind_ttc < threshold: fast approaching car -> True (conflict, block)
    - behind_ttc <= 0.0 or not amap_alive: sensor dead/invalid -> True (fail-safe block)
    """
    if not amap_alive:
        return True # fail-safe block

    mode = overtake_mode if overtake_mode in (0, 1, 2) else 1
    thr = {0: 1.8, 1: 2.5, 2: 3.5}.get(mode, 2.5)

    if behind_ttc <= 0.0:
        return True # invalid/offline sensor -> block
    if behind_ttc >= 99.0:
        return False # clear lane -> permit

    return behind_ttc < thr

class TestTtcAndLaneChangeGating(unittest.TestCase):

    def test_empty_lane_permits_lane_change(self):
        """F-32-01 Fix: On an empty lane with no approaching cars, lane change MUST NOT be blocked!"""
        # Scenario: Sensors alive, but no rear cars detected
        ttc = calculate_rear_ttc(main_lb_drel=None, lb_vrel=None, main_rb_drel=None, rb_vrel=None, sensor_alive=True)
        self.assertEqual(ttc, 99.0, "Empty lane should produce 99.0 clear sentinel")

        conflict = evaluate_rear_conflict(behind_ttc=ttc, overtake_mode=1, amap_alive=True)
        self.assertFalse(conflict, "Empty lane with no cars MUST NOT block lane change!")

    def test_approaching_vehicle_blocks_lane_change(self):
        """Fast approaching rear vehicle (TTC = 1.2s) MUST block lane change under Normal mode (2.5s)"""
        # Scenario: Rear left vehicle at -18m approaching at -15m/s (TTC = 1.2s)
        ttc = calculate_rear_ttc(main_lb_drel=-18000, lb_vrel=-15.0, main_rb_drel=None, rb_vrel=None, sensor_alive=True)
        self.assertAlmostEqual(ttc, 1.2, places=2)

        conflict = evaluate_rear_conflict(behind_ttc=ttc, overtake_mode=1, amap_alive=True)
        self.assertTrue(conflict, "Rear vehicle approaching at TTC 1.2s MUST block lane change!")

    def test_three_level_overtake_threshold_boundaries(self):
        """TTC = 2.0s boundary test across Aggressive (1.8s), Normal (2.5s), and Safe (3.5s)"""
        ttc = 2.0
        # Mode 0 (Aggressive, thr=1.8s): 2.0 >= 1.8 -> permit
        self.assertFalse(evaluate_rear_conflict(behind_ttc=ttc, overtake_mode=0, amap_alive=True))

        # Mode 1 (Normal, thr=2.5s): 2.0 < 2.5 -> block
        self.assertTrue(evaluate_rear_conflict(behind_ttc=ttc, overtake_mode=1, amap_alive=True))

        # Mode 2 (Safe, thr=3.5s): 2.0 < 3.5 -> block
        self.assertTrue(evaluate_rear_conflict(behind_ttc=ttc, overtake_mode=2, amap_alive=True))

    def test_sensor_offline_fail_safe_blocks(self):
        """When sensors or amapNavi are dead, system MUST fail-safe block (rear_conflict == True)"""
        # Sensor offline -> ttc = 0.0
        ttc = calculate_rear_ttc(main_lb_drel=None, lb_vrel=None, main_rb_drel=None, rb_vrel=None, sensor_alive=False)
        self.assertEqual(ttc, 0.0)
        self.assertTrue(evaluate_rear_conflict(behind_ttc=ttc, overtake_mode=1, amap_alive=True))

        # amapNavi service not alive
        self.assertTrue(evaluate_rear_conflict(behind_ttc=99.0, overtake_mode=1, amap_alive=False))

if __name__ == "__main__":
    unittest.main()
