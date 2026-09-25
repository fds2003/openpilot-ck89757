#!/usr/bin/env python3
"""
Unit test for right obstacle avoidance, oncoming vehicle detection,
solid-line borrowing permission, and immediate lane centering recovery.
"""
import time
import numpy as np
from types import SimpleNamespace
from cereal import log
from openpilot.selfdrive.controls.lib.lateral_planner import LateralPlanner, ObstacleItem

class DummyLead:
    def __init__(self, status=False, dRel=0.0, yRel=0.0, vRel=0.0, vLead=0.0):
        self.status = status
        self.dRel = dRel
        self.yRel = yRel
        self.vRel = vRel
        self.vLead = vLead

class DummyRadarState:
    def __init__(self):
        self.leadOne = DummyLead()
        self.leadRight = DummyLead()
        self.leadLeft = DummyLead()
        self.leadsRight = []
        self.leadsRight2 = []
        self.leadsLeft = []
        self.leadsLeft2 = []

class DummyModelV2:
    def __init__(self):
        self.position = SimpleNamespace(x=np.zeros(33), y=np.zeros(33), z=np.zeros(33), t=np.linspace(0, 2, 33))
        self.orientation = SimpleNamespace(x=np.zeros(33), y=np.zeros(33), z=np.zeros(33))
        self.laneLineProbs = [0.8, 0.8, 0.8, 0.8]
        self.laneLines = [
            SimpleNamespace(x=np.linspace(0, 100, 33), y=np.full(33, -3.5), t=np.linspace(0, 2, 33)),
            SimpleNamespace(x=np.linspace(0, 100, 33), y=np.full(33, -1.75), t=np.linspace(0, 2, 33)),
            SimpleNamespace(x=np.linspace(0, 100, 33), y=np.full(33, 1.75), t=np.linspace(0, 2, 33)),
            SimpleNamespace(x=np.linspace(0, 100, 33), y=np.full(33, 3.5), t=np.linspace(0, 2, 33)),
        ]
        self.roadEdges = [
            SimpleNamespace(x=np.linspace(0, 100, 33), y=np.full(33, -3.0), t=np.linspace(0, 2, 33)),
            SimpleNamespace(x=np.linspace(0, 100, 33), y=np.full(33, 3.0), t=np.linspace(0, 2, 33)),
        ]
        self.roadEdgeStds = [0.1, 0.1]
        self.meta = SimpleNamespace(
            desireState=[], desirePrediction=[], desire=log.Desire.none,
            distanceToRoadEdgeLeft=3.0, distanceToRoadEdgeRight=3.0,
            rightFrontBlind=0, leftFrontBlind=0, atcBsd=0
        )
        self.leadsV3 = []

class MockSubMaster:
    def __init__(self):
        self.seen = {'radarState': True, 'modelV2': True, 'carrotMan': False, 'controlsState': True, 'carState': True}
        self.alive = {'radarState': True, 'modelV2': True, 'carrotMan': False, 'controlsState': True, 'carState': True}
        self.frame = 100
        self.radarState = DummyRadarState()
        self.modelV2 = DummyModelV2()
        self.carState = SimpleNamespace(vEgo=12.0, standstill=False, steeringAngleDeg=0.0, useLaneLineSpeed=0)
        self.controlsState = SimpleNamespace(curvature=0.0)

    def __getitem__(self, item):
        return getattr(self, item)

def run_tests():
    CP = SimpleNamespace(
        wheelbase=3.05, centerToFront=1.5, mass=1900.0, tireStiffnessRear=100000.0,
        steerActuatorDelay=0.12, steerRatio=15.0
    )
    lp = LateralPlanner(CP)
    lp.right_avoid_dist_m = 1.0  # 100cm default

    print("=== Test 1: Right stationary broken-down car, Oncoming CLEAR ===")
    sm1 = MockSubMaster()
    # Right obstacle: 15m ahead, yRel = -1.6m (right), vLead = 0 (stationary)
    sm1.radarState.leadRight = DummyLead(status=True, dRel=15.0, yRel=-1.6, vRel=-12.0, vLead=0.0)
    # No oncoming vehicle on left
    obs_list1 = lp._extract_obstacles_and_oncoming(sm1)
    print(f"Extracted obstacles: {obs_list1}")
    print(f"Oncoming traffic detected: {lp.has_oncoming_traffic}")
    assert not lp.has_oncoming_traffic, "Expected oncoming traffic to be False"
    assert len(obs_list1) > 0, "Expected at least 1 obstacle"
    assert obs_list1[0].type == "parked", f"Expected parked obstacle, got {obs_list1[0].type}"

    lp._calc_obstacle_avoid_param(None, obs_list1)
    print(f"Calculated obs_smooth_offset: {lp.obs_smooth_offset:.3f} m (Negative means Left)")
    assert lp.obs_smooth_offset < -0.3, f"Expected left shift < -0.3, got {lp.obs_smooth_offset}"

    # Check solid line borrow permission:
    allow_borrow1 = (
        (lp.has_roadside_parked or lp.has_static_obstacle)
        and not lp.has_oncoming_traffic
        and lp.obs_smooth_offset < -0.15
    )
    print(f"Solid line borrowing allowed: {allow_borrow1}")
    assert allow_borrow1, "Expected allow_borrow_line to be True when oncoming is clear"

    print("\n=== Test 2: Right broken-down car, Oncoming TRAFFIC DETECTED ===")
    sm2 = MockSubMaster()
    sm2.radarState.leadRight = DummyLead(status=True, dRel=15.0, yRel=-1.6, vRel=-12.0, vLead=0.0)
    # Left oncoming vehicle approaching: 35m ahead, yRel = +1.8m (left), vLead = -12.0 m/s
    sm2.radarState.leadLeft = DummyLead(status=True, dRel=35.0, yRel=1.8, vRel=-24.0, vLead=-12.0)
    obs_list2 = lp._extract_obstacles_and_oncoming(sm2)
    print(f"Oncoming traffic detected: {lp.has_oncoming_traffic}")
    assert lp.has_oncoming_traffic, "Expected oncoming traffic to be True"

    lp._calc_obstacle_avoid_param(None, obs_list2)
    allow_borrow2 = (
        (lp.has_roadside_parked or lp.has_static_obstacle)
        and not lp.has_oncoming_traffic
        and lp.obs_smooth_offset < -0.15
    )
    print(f"Solid line borrowing allowed with oncoming car: {allow_borrow2}")
    assert not allow_borrow2, "Expected allow_borrow_line to be False when oncoming car is detected"

    print("\n=== Test 3: Right Pedestrian / E-bike (vLead = 4.0 m/s) ===")
    sm3 = MockSubMaster()
    # Right e-bike: 12m ahead, yRel = -1.3m, vLead = 4.0m/s
    sm3.radarState.leadRight = DummyLead(status=True, dRel=12.0, yRel=-1.3, vRel=-8.0, vLead=4.0)
    obs_list3 = lp._extract_obstacles_and_oncoming(sm3)
    print(f"Obstacle type: {obs_list3[0].type}")
    assert obs_list3[0].type in ("motorcycle", "pedestrian")
    lp._calc_obstacle_avoid_param(None, obs_list3)
    print(f"Calculated left shift for e-bike: {lp.obs_smooth_offset:.3f} m")
    assert lp.obs_smooth_offset < -0.3, "Expected significant left shift for e-bike"

    print("\n=== Test 4: Pass-by Completion and Immediate Centering Recovery ===")
    sm4 = MockSubMaster()
    # Obstacle is cleared (no targets in front)
    lp.passing_obstacle = True
    lp.passed_distance = 6.0  # > 5.2m car length passed
    lp._calc_obstacle_avoid_param(None, [])
    assert not lp.passing_obstacle, "Expected passing_obstacle to be False after clearing"
    print(f"Immediately returning to center: offset = {lp.obs_smooth_offset:.3f} m")
    # Simulate a few cycles of recovery
    for _ in range(5):
        lp._calc_obstacle_avoid_param(None, [])
    print(f"Offset after 5 frames of fast centering: {lp.obs_smooth_offset:.3f} m")
    assert abs(lp.obs_smooth_offset) < 0.05, f"Expected offset to be centered near 0.0, got {lp.obs_smooth_offset}"

    print("\nALL TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    run_tests()
