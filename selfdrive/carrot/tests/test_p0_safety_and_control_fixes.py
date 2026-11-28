#!/usr/bin/env python3
"""TDD tests for P0 safety and control fixes:
1. lane_planner_2.update_two_wheel_avoid coordinate sign (yRel: +left, -right)
2. carrot_serv._update_cmd preserving adbridge traffic_state when DETECT inactive
3. desire_helper laneChangeStarting TTC abort not overwritten in the same frame
"""
import ast
from collections import deque
import os
import types
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))


def _read_source(rel_path):
  with open(os.path.join(ROOT, rel_path), encoding="utf-8") as f:
    return f.read()


def _extract_method(rel_path, class_name, method_name, extra_globals=None):
  source = _read_source(rel_path)
  tree = ast.parse(source)
  for node in tree.body:
    if isinstance(node, ast.ClassDef) and node.name == class_name:
      for item in node.body:
        if isinstance(item, ast.FunctionDef) and item.name == method_name:
          mod = ast.Module(body=[item], type_ignores=[])
          ast.fix_missing_locations(mod)
          ns = dict(extra_globals or {})
          exec(compile(mod, rel_path, "exec"), ns)
          return ns[method_name]
  raise AssertionError(f"{class_name}.{method_name} not found in {rel_path}")


class TestTwoWheelAvoidSign(unittest.TestCase):

  def setUp(self):
    fn = _extract_method(
      "selfdrive/controls/lib/lane_planner_2.py",
      "LanePlanner",
      "update_two_wheel_avoid",
      {
        "TWO_WHEEL_MAX_LONG_DIST": 25.0,
        "TWO_WHEEL_AVOID_SHIFT": 0.55,
        "TWO_WHEEL_SHIFT_ALPHA": 0.12,
      },
    )
    self.lp = types.SimpleNamespace(
      two_wheel_avoid_shift=0.0,
      two_wheel_avoid_shift_smooth=0.0,
    )
    self.lp.update_two_wheel_avoid = types.MethodType(fn, self.lp)

  def test_right_side_target_triggers_left_avoid(self):
    # radarState.yRel: negative is right side
    self.lp.update_two_wheel_avoid([(10.0, -0.8, "bicycle")])
    self.assertGreater(self.lp.two_wheel_avoid_shift, 0.0)
    self.assertGreater(self.lp.two_wheel_avoid_shift_smooth, 0.0)

  def test_left_side_target_does_not_trigger_avoid(self):
    # radarState.yRel: positive is left side, should NOT trigger leftward shift
    self.lp.update_two_wheel_avoid([(10.0, 0.8, "bicycle")])
    self.assertEqual(self.lp.two_wheel_avoid_shift, 0.0)


class TestBridgeTrafficStatePreserved(unittest.TestCase):

  def setUp(self):
    fn = _extract_method("selfdrive/carrot/carrot_serv.py", "CarrotServ", "_update_cmd")
    self.serv = types.SimpleNamespace(
      carrotCmdIndex=0,
      carrotCmdIndex_last=0,
      carrotCmd="",
      carrotArg="",
      traffic_light_q=deque(maxlen=2),
      traffic_light_count=-1,
      traffic_state=0,
      _handle_detect_command=lambda arg: None,
      _handle_speed_limit_command=lambda arg: None,
    )
    self.serv._update_cmd = types.MethodType(fn, self.serv)

  def test_adbridge_state_not_cleared_when_detect_inactive(self):
    # adbridge sets traffic_state=1 while DETECT is inactive (traffic_light_count == -1)
    self.serv.traffic_light_count = -1
    self.serv.traffic_state = 1
    self.serv._update_cmd()
    self.assertEqual(self.serv.traffic_state, 1)

  def test_detect_expiration_clears_traffic_state(self):
    # DETECT active countdown reaches expiration: 0 -> -1 clears traffic_state
    self.serv.traffic_light_count = 0
    self.serv.traffic_state = 2
    self.serv._update_cmd()
    self.assertEqual(self.serv.traffic_light_count, -1)
    self.assertEqual(self.serv.traffic_state, 0)


class TestDesireHelperTtcAbortExclusive(unittest.TestCase):

  def test_abort_branch_is_mutually_exclusive_with_finishing(self):
    source = _read_source("selfdrive/controls/lib/desire_helper.py")
    tree = ast.parse(source)
    found_abort_if = None
    for node in ast.walk(tree):
      if isinstance(node, ast.If) and isinstance(node.test, ast.Name) and node.test.id == "abort":
        found_abort_if = node
        break
    self.assertIsNotNone(found_abort_if, "if abort: branch not found in desire_helper.py")
    # Must have an orelse (elif) leading to lane_change_prob < 0.02 transition
    self.assertTrue(
      len(found_abort_if.orelse) == 1 and isinstance(found_abort_if.orelse[0], ast.If),
      "if abort: must chain with elif lane_change_prob < 0.02 ... so abort is not overwritten in the same frame!",
    )


if __name__ == "__main__":
  unittest.main()
