import time
import numpy as np
from openpilot.common.realtime import DT_MDL
from openpilot.common.swaglog import cloudlog
from openpilot.selfdrive.controls.lib.lateral_mpc_lib.lat_mpc import LateralMpc
from openpilot.selfdrive.controls.lib.lateral_mpc_lib.lat_mpc import N as LAT_MPC_N
from openpilot.selfdrive.controls.lib.drive_helpers import CONTROL_N, MIN_SPEED, get_speed_error
import cereal.messaging as messaging
from cereal import log
from openpilot.common.params import Params
from openpilot.selfdrive.controls.lib.lane_planner_2 import LanePlanner
from collections import deque

TRAJECTORY_SIZE = 33
CAMERA_OFFSET = 0.04

PATH_COST = 1.0
LATERAL_MOTION_COST = 0.11
LATERAL_ACCEL_COST = 0.0
LATERAL_JERK_COST = 0.04
STEERING_RATE_COST = 700.0

# ===================== 导航联动优化（与 amap_navi 对接）=====================
NAV_TIMEOUT = 3.5
last_nav_update = 0.0
nav_hold_mode = False

def is_nav_active():
    global last_nav_update, nav_hold_mode
    try:
        from openpilot.selfdrive.carrot.amap_navi import NAV_ACTIVE, NAV_LAST_UPDATE
        now = time.time()
        if NAV_ACTIVE and (now - NAV_LAST_UPDATE) <= NAV_TIMEOUT:
            last_nav_update = now
            nav_hold_mode = True
            return True
        if nav_hold_mode and (now - last_nav_update) <= 2.0:
            return True
        nav_hold_mode = False
        return False
    except:
        return False
# =========================================================================

class LateralPlanner:
  def __init__(self, CP, debug=False):
    self.factor1 = CP.wheelbase - CP.centerToFront
    self.factor2 = (CP.centerToFront * CP.mass) / (CP.wheelbase * CP.tireStiffnessRear)
    self.last_cloudlog_t = 0
    self.solution_invalid_cnt = 0

    self.path_xyz = np.zeros((TRAJECTORY_SIZE, 3))
    self.velocity_xyz = np.zeros((TRAJECTORY_SIZE, 3))
    self.v_plan = np.zeros((TRAJECTORY_SIZE,))
    self.x_sol = np.zeros((TRAJECTORY_SIZE, 4), dtype=np.float32)
    self.v_ego = MIN_SPEED
    self.l_lane_change_prob = 0.0
    self.r_lane_change_prob = 0.0
    self.debug_mode = debug

    self.params = Params()
    self.latDebugText = ""
    self.LP = LanePlanner()
    self.readParams = 0
    self.lanelines_active = False
    self.lanelines_active_tmp = False
    self.useLaneLineSpeedApply = self.params.get_int("UseLaneLineSpeed")
    self.pathOffset = float(self.params.get_int("PathOffset")) * 0.01
    self.useLaneLineMode = False

    self.plan_a = np.zeros((TRAJECTORY_SIZE, ))
    self.plan_yaw = np.zeros((TRAJECTORY_SIZE,))
    self.plan_yaw_rate = np.zeros((TRAJECTORY_SIZE,))
    self.t_idxs = np.arange(TRAJECTORY_SIZE)
    self.y_pts = np.zeros((TRAJECTORY_SIZE,))
    self.d_path_w_lines_xyz = np.zeros((TRAJECTORY_SIZE, 3))

    self.lat_mpc = LateralMpc()
    self.reset_mpc(np.zeros(4))
    self.curve_speed = 0
    self.lanemode_possible_count = 0
    self.laneless_only = True

  def reset_mpc(self, x0=None):
    if x0 is None:
      x0 = np.zeros(4)
    self.x0 = x0
    self.lat_mpc.reset(x0=self.x0)

  def update(self, sm, carrot):
    global LATERAL_ACCEL_COST, LATERAL_JERK_COST, STEERING_RATE_COST
    self.readParams -= 1
    if self.readParams <= 0:
      self.readParams = 100
      self.useLaneLineSpeedApply = sm['carState'].useLaneLineSpeed
      self.pathOffset = float(self.params.get_int("PathOffset")) * 0.01
      self.lateralPathCost = self.params.get_float("LatMpcPathCost") * 0.01
      self.lateralMotionCost = self.params.get_float("LatMpcMotionCost") * 0.01
      LATERAL_ACCEL_COST = self.params.get_float("LatMpcAccelCost") * 0.01
      LATERAL_JERK_COST = self.params.get_float("LatMpcJerkCost") * 0.01
      STEERING_RATE_COST = self.params.get_float("LatMpcSteeringRateCost")

    measured_curvature = sm['controlsState'].curvature
    v_ego_car = sm['carState'].vEgo
    self.curve_speed = sm['carrotMan'].vTurnSpeed

    # ===================== 导航联动：弯道更柔、提前预判 =====================
    nav_active = is_nav_active()
    if nav_active:
        if measured_curvature > 0.0:
            measured_curvature *= np.interp(self.v_ego, [3.0, 6.0, 10.0], [1.0, 0.85, 0.75])
        if measured_curvature > 0.022:
            measured_curvature = 0.022
    else:
        if measured_curvature > 0.0:
            measured_curvature *= np.interp(self.v_ego, [3.0, 5.0, 8.0], [1.0, 0.90, 0.80])
        if measured_curvature > 0.025:
            measured_curvature = 0.025
    # ======================================================================

    md = sm['modelV2']
    if len(md.position.x) == TRAJECTORY_SIZE and len(md.orientation.x) == TRAJECTORY_SIZE:
      self.path_xyz = np.column_stack([md.position.x, md.position.y, md.position.z])
      self.t_idxs = np.array(md.position.t)
      self.plan_yaw = np.array(md.orientation.z)
      self.plan_yaw_rate = np.array(md.orientationRate.z)
      self.velocity_xyz = np.column_stack([md.velocity.x, md.velocity.y, md.velocity.z])
      car_speed = np.linalg.norm(self.velocity_xyz, axis=1) - get_speed_error(md, v_ego_car)
      self.v_plan = np.clip(car_speed, MIN_SPEED, np.inf)
      self.v_ego = self.v_plan[0]
      self.plan_a = np.array(md.acceleration.x)

      if md.velocity.x[-1] < md.velocity.x[0] * 0.7:
        self.lanemode_possible_count = 0
        self.laneless_only = True
      else:
        self.lanemode_possible_count += 1
        if self.lanemode_possible_count > int(1/DT_MDL):
          self.laneless_only = False

    self.LP.parse_model(md)

    if self.v_ego < 18:
        self.useLaneLineMode = False
    else:
        if self.useLaneLineSpeedApply == 0 or self.laneless_only:
          self.useLaneLineMode = False
        else:
          self.useLaneLineMode = True

    curvature = measured_curvature
    self.LP.curvature = curvature

    # ===================== 导航模式：更顺滑、不抢方向盘 =====================
    if nav_active:
        self.LP.lane_change_multiplier = 0.0
    else:
        if md.meta.desire != log.Desire.none or carrot.atc_active:
          self.LP.lane_change_multiplier = 0.0
        else:
          self.LP.lane_change_multiplier = 1.0
    # ======================================================================

    self.LP.lanefull_mode = self.useLaneLineMode
    self.LP.lane_width_left = md.meta.laneWidthLeft
    self.LP.lane_width_right = md.meta.laneWidthRight
    self.LP.curvature = curvature

    self.path_xyz, self.lanelines_active = self.LP.get_d_path(sm['carState'], self.v_ego, self.t_idxs, self.path_xyz, self.curve_speed)
    self.path_xyz[:, 1] += self.pathOffset

    self.lat_mpc.set_weights(self.lateralPathCost, self.lateralMotionCost,
                             LATERAL_ACCEL_COST, LATERAL_JERK_COST,
                             STEERING_RATE_COST)

    y_pts = self.path_xyz[:LAT_MPC_N+1, 1]
    heading_pts = self.plan_yaw[:LAT_MPC_N+1]
    yaw_rate_pts = self.plan_yaw_rate[:LAT_MPC_N+1]
    self.y_pts = y_pts

    lateral_factor = np.clip(self.factor1 - (self.factor2 * self.v_plan**2), 0.0, np.inf)
    p = np.column_stack([self.v_plan, lateral_factor])
    self.lat_mpc.run(self.x0, p, y_pts, heading_pts, yaw_rate_pts)
    self.x0[3] = np.interp(DT_MDL, self.t_idxs[:LAT_MPC_N + 1], self.lat_mpc.x_sol[:, 3])

    mpc_nans = np.isnan(self.lat_mpc.x_sol[:, 3]).any()
    t = time.monotonic()
    if mpc_nans or self.lat_mpc.solution_status != 0:
      self.reset_mpc()
      self.x0[3] = measured_curvature * self.v_ego
      if t > self.last_cloudlog_t + 5.0:
        self.last_cloudlog_t = t
        cloudlog.warning("Lateral mpc - nan: True")

    if self.lat_mpc.cost > 1e6 or mpc_nans:
      self.solution_invalid_cnt += 1
    else:
      self.solution_invalid_cnt = 0

    self.x_sol = self.lat_mpc.x_sol

  def publish(self, sm, pm, carrot):
    plan_solution_valid = self.solution_invalid_cnt < 2
    plan_send = messaging.new_message('lateralPlan')
    plan_send.valid = sm.all_checks(service_list=['carState', 'controlsState', 'modelV2'])

    lateralPlan = plan_send.lateralPlan
    lateralPlan.modelMonoTime = sm.logMonoTime['modelV2']
    lateralPlan.dPathPoints = self.y_pts.tolist()
    lateralPlan.psis = self.lat_mpc.x_sol[0:CONTROL_N, 2].tolist()
    lateralPlan.distances = self.lat_mpc.x_sol[0:CONTROL_N, 0].tolist()

    if len(self.v_plan) == TRAJECTORY_SIZE:
      lateralPlan.curvatures = (self.lat_mpc.x_sol[0:CONTROL_N, 3] / self.v_plan[0:CONTROL_N]).tolist()
    else:
      lateralPlan.curvatures = (self.lat_mpc.x_sol[0:CONTROL_N, 3] / self.v_ego).tolist()

    lateralPlan.curvatureRates = [float(x.item() / self.v_ego) for x in self.lat_mpc.u_sol[0:CONTROL_N - 1]] + [0.0]
    lateralPlan.mpcSolutionValid = bool(plan_solution_valid)
    lateralPlan.solverExecutionTime = self.lat_mpc.solve_time

    if self.debug_mode:
      lateralPlan.solverCost = self.lat_mpc.cost
      lateralPlan.solverState = log.LateralPlan.SolverState.new_message()
      lateralPlan.solverState.x = self.lat_mpc.x_sol.tolist()
      lateralPlan.solverState.u = self.lat_mpc.u_sol.flatten().tolist()

    lateralPlan.useLaneLines = self.lanelines_active
    lateralPlan.laneWidth = float(self.LP.lane_width)
    lateralPlan.position.x = self.x_sol[:, 0].tolist()
    lateralPlan.position.y = self.x_sol[:, 1].tolist()
    lateralPlan.position.z = self.path_xyz[:, 2].tolist()

    debugText = (
      f"{'lanemode' if self.lanelines_active else 'laneless'} | " +
      f"{self.LP.lane_width_left:.1f}m | {self.LP.lane_width:.1f}m | {self.LP.lane_width_right:.1f}m | " +
      f"offset={self.LP.offset_total * 100:.1f}cm turn={np.clip(self.curve_speed, -200, 200):.0f}km/h"
    )
    lateralPlan.latDebugText = debugText
    pm.send('lateralPlan', plan_send)