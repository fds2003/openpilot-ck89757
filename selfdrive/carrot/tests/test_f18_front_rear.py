#!/usr/bin/env python3
"""
TDD Test for F-18: compute_delta_v_for_front_rear copy-paste bug.

RED state (before patch): delta_v_front is computed via for_rear, not for_front.
GREEN state (after patch): delta_v_front uses for_front, semantics are correct.

Test strategy: source-level scan + behavioral simulation.
"""
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
CARROT_SERV = os.path.join(ROOT, "selfdrive", "carrot", "carrot_serv.py")


class TestF18FrontRearCopyPaste(unittest.TestCase):

    # ------------------------------------------------------------------
    # 1. Source-level check: for_front MUST be called in front_rear
    # ------------------------------------------------------------------
    def test_front_rear_calls_for_front(self):
        """F-18 RED: the current buggy code calls for_rear for BOTH front and rear.
        GREEN: line 'delta_v_front = self.compute_delta_v_for_front(' must exist."""
        with open(CARROT_SERV, encoding="utf-8") as f:
          text = f.read()

        # Find the compute_delta_v_for_front_rear method body
        m = re.search(r"def compute_delta_v_for_front_rear\(.*?(?=\n  def |\Z)", text, re.DOTALL)
        self.assertIsNotNone(m, "compute_delta_v_for_front_rear not found in carrot_serv.py")
        body = m.group(0)

        # RED check: body must NOT use for_rear for delta_v_front
        front_with_rear = re.search(
          r"delta_v_front\s*=\s*self\.compute_delta_v_for_rear\(", body
        )
        front_with_front = re.search(
          r"delta_v_front\s*=\s*self\.compute_delta_v_for_front\(", body
        )
        if front_with_front:
          # GREEN state — for_front is used, good
          self.assertIsNone(front_with_rear,
            "compute_delta_v_for_front_rear must NOT call for_rear for delta_v_front (F-18 bug)")
        else:
          # RED state — raise to make test fail
          self.fail(
            "F-18 RED: delta_v_front is computed via compute_delta_v_for_rear, "
            "but it should use compute_delta_v_for_front. "
            "Apply carrot_f18_f22.patch to fix."
          )

    # Behavioral tests: monkeypatch import failure to skip if openpilot namespace is not importable
    def test_front_slower_car_gets_positive_delta_v(self):
        """If lead vehicle (front) is significantly slower than ego,
        compute_delta_v_for_front MUST return a positive delta_v (accelerate to catch up)."""
        import importlib
        try:
          module = importlib.import_module("openpilot.selfdrive.carrot.carrot_serv")
        except Exception as e:
          self.skipTest(f"openpilot namespace not importable in this environment: {e}")
        CarrotServ = module.CarrotServ

        # Minimal mock — bypass __init__ network setup
        serv = CarrotServ.__new__(CarrotServ)
        # Stub required attributes
        serv.lf_drel = None
        serv.lb_drel = None
        serv.rf_drel = None
        serv.rb_drel = None
        serv.lf_vrel = None
        serv.lb_vrel = None
        serv.rf_vrel = None
        serv.rb_vrel = None
        serv.atc_speed_delta = None
        serv.bsd_v_ego_kph = None
        serv.bsd_speed_keep_time = -1
        serv.nRoadLimitSpeed = 80
        serv.active_carrot = 0
        serv.roadcate = 8
        serv.fork_speed_keep_time = -1
        serv.atc_speed_delta_new = None

        # f_vrel < 0 means lead is slower than ego → for_front should accelerate (positive)
        # b_vrel = 0 means rear is at same speed
        delta_v = serv.compute_delta_v_for_front_rear(
          f_drel_mm=10000,  # 10 m
          f_vrel=-3.0,       # front car is 3 m/s slower
          b_drel_mm=5000,   # 5 m
          b_vrel=0.0,
          v_ego=20.0,
          speed_up_enable=True,
          decel_priority=False
        )
        # If F-18 fix applied: front (slower) should produce a POSITIVE delta_v
        self.assertGreater(
          delta_v, 0.0,
          "F-18: front car is slower than ego → delta_v should be positive "
          "(accelerate to close gap). Got delta_v=%.2f. "
          "Likely still using for_rear logic (F-18 bug not fixed)." % delta_v
        )

    # ------------------------------------------------------------------
    # 3. Behavioral: front car faster → negative delta_v (decelerate)
    # ------------------------------------------------------------------
    def test_front_faster_car_gets_negative_delta_v(self):
        """If front vehicle is faster than ego, delta_v should be <= 0
        (no need to accelerate, or decelerate)."""
        import importlib
        try:
          module = importlib.import_module("openpilot.selfdrive.carrot.carrot_serv")
        except Exception as e:
          self.skipTest(f"openpilot namespace not importable in this environment: {e}")
        CarrotServ = module.CarrotServ

        serv = CarrotServ.__new__(CarrotServ)
        serv.lf_drel = None; serv.lb_drel = None
        serv.rf_drel = None; serv.rb_drel = None
        serv.lf_vrel = None; serv.lb_vrel = None
        serv.rf_vrel = None; serv.rb_vrel = None
        serv.atc_speed_delta = None
        serv.bsd_v_ego_kph = None
        serv.bsd_speed_keep_time = -1
        serv.nRoadLimitSpeed = 80
        serv.active_carrot = 0
        serv.roadcate = 8
        serv.fork_speed_keep_time = -1
        serv.atc_speed_delta_new = None

        delta_v = serv.compute_delta_v_for_front_rear(
          f_drel_mm=8000,   # 8 m
          f_vrel=5.0,        # front car is 5 m/s FASTER
          b_drel_mm=99999,  # far away
          b_vrel=0.0,
          v_ego=20.0,
          speed_up_enable=False,
          decel_priority=True
        )
        self.assertLessEqual(
          delta_v, 0.0,
          "F-18: front car is faster AND decel_priority → delta_v must be <= 0. "
          "Got %.2f." % delta_v
        )

if __name__ == "__main__":
    unittest.main()
