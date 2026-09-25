#!/usr/bin/env python3
import math
from typing import SupportsFloat
from cereal import car, log
import cereal.messaging as messaging
from openpilot.common.conversions import Conversions as CV
from openpilot.common.params import Params
from openpilot.common.realtime import config_realtime_process, Priority, Ratekeeper
from openpilot.common.swaglog import cloudlog
import numpy as np
from collections import deque
from opendbc.car.car_helpers import interfaces
from opendbc.car.vehicle_model import VehicleModel
from openpilot.selfdrive.controls.lib.drive_helpers import clip_curvature, get_lag_adjusted_curvature
from openpilot.selfdrive.controls.lib.latcontrol import LatControl, MIN_LATERAL_CONTROL_SPEED
from openpilot.selfdrive.controls.lib.latcontrol_pid import LatControlPID
from openpilot.selfdrive.controls.lib.latcontrol_angle import LatControlAngle, STEER_ANGLE_SATURATION_THRESHOLD
from openpilot.selfdrive.controls.lib.latcontrol_torque import LatControlTorque
from openpilot.selfdrive.controls.lib.longcontrol import LongControl
from openpilot.common.realtime import DT_CTRL, DT_MDL
from openpilot.selfdrive.modeld.constants import ModelConstants
from selfdrive.modeld.modeld import LAT_SMOOTH_SECONDS

State = log.SelfdriveState.OpenpilotState
LaneChangeState = log.LaneChangeState
LaneChangeDirection = log.LaneChangeDirection
ACTUATOR_FIELDS = tuple(car.CarControl.Actuators.schema.fields.keys())

class Controls:
  def __init__(self) -> None:
    self.params = Params()
    cloudlog.info("controlsd is waiting for CarParams")
    self.CP = messaging.log_from_bytes(self.params.get("CarParams", block=True), car.CarParams)
    cloudlog.info("controlsd got CarParams")
    self.CI = interfaces[self.CP.carFingerprint](self.CP)
    self.disable_dm = False
    self.sm = messaging.SubMaster(['liveParameters', 'liveTorqueParameters', 'modelV2', 'selfdriveState',
                                   'liveCalibration', 'liveLocationKalman', 'longitudinalPlan', 'carState', 'carOutput',
                                   'liveDelay', 'carrotMan', 'lateralPlan', 'radarState',
                                   'driverMonitoringState', 'onroadEvents', 'driverAssistance'], poll='selfdriveState')
    self.pm = messaging.PubMaster(['carControl', 'controlsState'])
    self.steer_limited_by_controls = False
    self.curvature = 0.0
    self.desired_curvature = 0.0
    self.yStd = 0.0
    self.side_state = {
        "left":  {"main": {"dRel": None, "lat": None}, "sub": {"dRel": None, "lat": None}},
        "right": {"main": {"dRel": None, "lat": None}, "sub": {"dRel": None, "lat": None}},
    }
    self.LoC = LongControl(self.CP)
    self.aeb_active = False
    self.aeb_hold_frames = 0
    self.VM = VehicleModel(self.CP)
    self.LaC: LatControl
    if self.CP.steerControlType == car.CarParams.SteerControlType.angle:
      self.LaC = LatControlAngle(self.CP, self.CI)
    elif self.CP.lateralTuning.which() == 'pid':
      self.LaC = LatControlPID(self.CP, self.CI)
    elif self.CP.lateralTuning.which() == 'torque':
      self.LaC = LatControlTorque(self.CP, self.CI)

  def update(self):
    self.sm.update(15)

  def state_control(self):
    CS = self.sm['carState']
    lp = self.sm['liveParameters']
    x = max(lp.stiffnessFactor, 0.1)
    sr = max(lp.steerRatio, 0.1) * self.params.get_float("SteerRatioRate") / 100.0
    custom_sr = self.params.get_float("CustomSR") / 10.0
    sr = max(custom_sr if custom_sr > 1.0 else sr, 0.1)
    self.VM.update_params(x, sr)
    steer_angle_without_offset = math.radians(CS.steeringAngleDeg - lp.angleOffsetDeg)
    self.curvature = -self.VM.calc_curvature(steer_angle_without_offset, CS.vEgo, lp.roll)

    if self.CP.lateralTuning.which() == 'torque':
      torque_params = self.sm['liveTorqueParameters']
      if self.sm.all_checks(['liveTorqueParameters']) and torque_params.useParams:
        self.LaC.update_live_torque_params(torque_params.latAccelFactorFiltered, torque_params.latAccelOffsetFiltered,
                                           torque_params.frictionCoefficientFiltered)

    long_plan = self.sm['longitudinalPlan']
    model_v2 = self.sm['modelV2']
    CC = car.CarControl.new_message()
    CC.enabled = self.sm['selfdriveState'].enabled

    gear = car.CarState.GearShifter
    driving_gear = CS.gearShifter not in (gear.neutral, gear.park, gear.reverse, gear.unknown)
    lateral_enabled = driving_gear
    standstill = abs(CS.vEgo) <= max(self.CP.minSteerSpeed, MIN_LATERAL_CONTROL_SPEED) or CS.standstill
    # 红灯右转：停住+右灯 → 横向保持激活
    if CS.rightBlinker and CS.standstill and CS.vEgo < 0.5:
        standstill = False
    CC.latActive = ((self.sm['selfdriveState'].active or lateral_enabled) and CS.latEnabled and
                    not CS.steerFaultTemporary and not CS.steerFaultPermanent and not standstill)

    CC.longActive = CC.enabled and not any(e.overrideLongitudinal for e in self.sm['onroadEvents']) and self.CP.openpilotLongitudinalControl

    # ===================== 强制开启障碍物避让，不受ACC、自动油门状态限制 =====================
    self.allow_obstacle_avoid = True

    actuators = CC.actuators
    actuators.longControlState = self.LoC.long_control_state

    if model_v2.meta.laneChangeState != LaneChangeState.off:
      CC.leftBlinker = model_v2.meta.laneChangeDirection == LaneChangeDirection.left
      CC.rightBlinker = model_v2.meta.laneChangeDirection == LaneChangeDirection.right

    if not CC.latActive:
      self.LaC.reset()
    if not CC.longActive:
      self.LoC.reset()

    pid_accel_limits = self.CI.get_pid_accel_limits(self.CP, CS.vEgo, CS.vCruise * CV.KPH_TO_MS)
    t_since_plan = (self.sm.frame - self.sm.recv_frame['longitudinalPlan']) * DT_CTRL
    accel, aTarget, jerk = self.LoC.update(CC.longActive, CS, long_plan, pid_accel_limits, t_since_plan, self.sm['radarState'])
    actuators.accel = float(accel)
    actuators.aTarget = float(aTarget)
    actuators.jerk = float(jerk)

    lat_plan = self.sm['lateralPlan']
    curve_speed_abs = abs(self.sm['carrotMan'].vTurnSpeed)
    self.lanefull_mode_enabled = (lat_plan.useLaneLines and curve_speed_abs > self.params.get_int("UseLaneLineCurveSpeed"))
    lat_smooth_seconds = LAT_SMOOTH_SECONDS
    steer_actuator_delay = self.params.get_float("SteerActuatorDelay") * 0.01
    if steer_actuator_delay == 0.0:
      steer_actuator_delay = self.sm['liveDelay'].lateralDelay 

    if len(model_v2.position.yStd) > 0:
      yStd = np.interp(steer_actuator_delay + lat_smooth_seconds, ModelConstants.T_IDXS, model_v2.position.yStd)
      self.yStd = yStd * 0.02 + self.yStd * 0.98
    else:
      self.yStd = 0.0
    
    if not CC.latActive:
      new_desired_curvature = self.curvature
    elif self.lanefull_mode_enabled:
      if len(lat_plan.curvatures) == 0:
        new_desired_curvature = self.curvature
      else:
        def smooth_value(val, prev_val, tau):
          alpha = 1 - np.exp(-DT_CTRL / tau) if tau > 0 else 1
          return alpha * val + (1 - alpha) * prev_val
        curvature = get_lag_adjusted_curvature(self.CP, CS.vEgo, lat_plan.psis, lat_plan.curvatures, steer_actuator_delay + lat_smooth_seconds, lat_plan.distances)
        new_desired_curvature = smooth_value(curvature, self.desired_curvature, lat_smooth_seconds)
    else:
      new_desired_curvature = model_v2.action.desiredCurvature

    if CS.vEgo < 11.1:
        speed_factor = max(0.6, 0.6 + 0.4 * (CS.vEgo / 11.1))
        new_desired_curvature *= speed_factor

    self.desired_curvature, curvature_limited = clip_curvature(CS.vEgo, self.desired_curvature, new_desired_curvature, lp.roll)
    actuators.curvature = float(self.desired_curvature)
    steer, steeringAngleDeg, lac_log = self.LaC.update(CC.latActive, CS, self.VM, lp,
                                                       self.steer_limited_by_controls, self.desired_curvature,
                                                       self.sm['liveLocationKalman'], curvature_limited,
                                                       model_data=self.sm['modelV2'])
    actuators.torque = float(steer)
    actuators.steeringAngleDeg = float(steeringAngleDeg)
    actuators.yStd = float(self.yStd)

    for p in ACTUATOR_FIELDS:
      attr = getattr(actuators, p)
      if not isinstance(attr, SupportsFloat):
        continue
      if not math.isfinite(attr):
        cloudlog.error(f"actuators.{p} not finite {actuators.to_dict()}")
        setattr(actuators, p, 0.0)

    return CC, lac_log

  def _update_side(self, side: str, leads2, road_edge, bsd_state, hudControl):
      def ema(prev, curr, a=0.02):
        return curr if prev is None else prev * (1 - a) + curr * a
      def set_hud(side_cap, name, val):
        setattr(hudControl, f"lead{side_cap}{name}", float(val if val is not None else 0.0))
        
      st = self.side_state[side]
      if road_edge <= 2.0 or not leads2:
        st["main"] = {"dRel": None, "lat": None}
        st["sub"]  = {"dRel": None, "lat": None}
        if not bsd_state:
          return
      lead_main = leads2[0] if len(leads2) > 0 else None
      side_cap = side.capitalize()
      if bsd_state:
        set_hud(side_cap, "Dist2", 1)
        set_hud(side_cap, "Lat2",  3.2)
      elif len(leads2) > 1 and lead_main.dRel < 10:
        st["sub"]["dRel"] = ema(st["sub"]["dRel"], lead_main.dRel)
        st["sub"]["lat"]  = ema(st["sub"]["lat"],  abs(lead_main.dPath))
        set_hud(side_cap, "Dist2", st["sub"]["dRel"])
        set_hud(side_cap, "Lat2",  st["sub"]["lat"])
        lead_main = leads2[1]
      if len(leads2) > 0:
        st["main"]["dRel"] = ema(st["main"]["dRel"], lead_main.dRel)
        st["main"]["lat"]  = ema(st["main"]["lat"],  abs(lead_main.dPath))
        set_hud(side_cap, "Dist", st["main"]["dRel"])
        set_hud(side_cap, "Lat",  st["main"]["lat"])

  def publish(self, CC, lac_log):
    CS = self.sm['carState']
    orientation_value = list(self.sm['liveLocationKalman'].calibratedOrientationNED.value)
    if len(orientation_value) > 2:
      CC.orientationNED = orientation_value
    angular_rate_value = list(self.sm['liveLocationKalman'].angularVelocityCalibrated.value)
    if len(angular_rate_value) > 2:
      CC.angularVelocity = angular_rate_value
    acceleration_value = list(self.sm['liveLocationKalman'].accelerationCalibrated.value)
    if len(acceleration_value) > 2:
      if abs(acceleration_value[0]) > 16.0:
        print("Collision detected. disable openpilot, restart")
        self.params.put_bool("OpenpilotEnabledToggle", False)
        self.params.put_int("SoftRestartTriggered", 1)

    CC.cruiseControl.override = CC.enabled and not CC.longActive and self.CP.openpilotLongitudinalControl
    CC.cruiseControl.cancel = CS.cruiseState.enabled and (not CC.enabled or not self.CP.pcmCruise)
    desired_kph = min(CS.vCruiseCluster, self.sm['carrotMan'].desiredSpeed)
    setSpeed = float(desired_kph * CV.KPH_TO_MS)
    speeds = self.sm['longitudinalPlan'].speeds
    if len(speeds):
      CC.cruiseControl.resume = CC.enabled and CS.cruiseState.standstill and speeds[-1] > 0.1
      vCluRatio = CS.vCluRatio if CS.vCluRatio > 0.5 else 1.0
      setSpeed = speeds[-1] / vCluRatio

    hudControl = CC.hudControl
    hudControl.activeCarrot = self.sm['carrotMan'].activeCarrot
    hudControl.atcDistance = self.sm['carrotMan'].xDistToTurn

    lp = self.sm['longitudinalPlan']
    carrotMan = self.sm['carrotMan']
    radarState = self.sm['radarState']
    leadOne = radarState.leadOne

    if self.CP.pcmCruise:
      # 1. 红灯防闯保护 (Stock ACC)
      # 如果检测到红灯且前方无前车（前雷达无跟随目标），接近停止线时主动切断巡航油门
      has_lead = leadOne.status
      is_red_light = (lp.trafficState == 1 or carrotMan.trafficState == 1)
      if CC.enabled and is_red_light and not has_lead:
        d_to_stop = carrotMan.xDistToTurn if 0 < carrotMan.xDistToTurn < 100 else 25.0
        if d_to_stop <= 25.0 or (CS.vEgo * CV.MS_TO_KPH <= 35.0 and d_to_stop <= 35.0) or desired_kph <= 15:
          CC.cruiseControl.cancel = True

      # 2. 弯道/拐弯防高速拖拽保护 (Stock ACC 最低 30km/h 物理限制)
      # 在直角转弯（left/right turn）且入弯距离近、期望转弯速度 < 26km/h 时，
      # 原厂定速 30km/h 偏快，主动 Cancel 巡航切断油门，由横向控制（latActive 在 D 档常驻）平顺转向过弯
      is_turning = carrotMan.xTurnInfo in [1, 2]
      if CC.enabled and is_turning:
        if 0 < carrotMan.xDistToTurn < 22 and desired_kph < 26 and CS.vEgo * CV.MS_TO_KPH > 22.0:
          CC.cruiseControl.cancel = True

      speed_from_pcm = self.params.get_int("SpeedFromPCM")
      if speed_from_pcm == 1:
        hudControl.setSpeed = float(CS.vCruiseCluster * CV.KPH_TO_MS)
      elif speed_from_pcm == 2:
        hudControl.setSpeed = float(max(20/3.6, desired_kph * CV.KPH_TO_MS))
      elif speed_from_pcm == 3:
        hudControl.setSpeed = setSpeed if lp.xState == 3 else float(desired_kph * CV.KPH_TO_MS)
      else:
        hudControl.setSpeed = float(max(20/3.6, setSpeed))
    else:
      hudControl.setSpeed = setSpeed if lp.xState == 3 else float(desired_kph * CV.KPH_TO_MS)

    hudControl.speedVisible = CC.enabled
    hudControl.lanesVisible = CC.enabled
    hudControl.leadVisible = self.sm['longitudinalPlan'].hasLead
    hudControl.leadDistanceBars = self.sm['selfdriveState'].personality.raw + 1
    hudControl.visualAlert = self.sm['selfdriveState'].alertHudVisual

    radarState = self.sm['radarState']
    leadOne = radarState.leadOne
    hudControl.leadDistance = leadOne.dRel if leadOne.status else 0
    hudControl.leadRelSpeed = leadOne.vRel if leadOne.status else 0
    hudControl.leadRadar = 1 if leadOne.radar else 0
    hudControl.leadDPath = leadOne.dPath

    # 视觉前向目标兜底 (若雷达未检出前车但视觉网络高置信度识别前车)
    if (not leadOne.status or hudControl.leadDistance <= 0.1) and len(self.sm['modelV2'].leadsV3) > 0:
      vis_lead = self.sm['modelV2'].leadsV3[0]
      if vis_lead.prob > 0.55:
        hudControl.leadDistance = float(vis_lead.x[0])
        hudControl.leadRelSpeed = float(vis_lead.v[0])
        hudControl.leadRadar = 0
        hudControl.leadDPath = float(vis_lead.y[0])
        hudControl.leadVisible = True

    # ------------------ 全场景紧急防碰撞与主动刹停 (AEB) ------------------
    custom_aeb = self.params.get_int("CustomAEB")
    if custom_aeb > 0:
      v_ego = CS.vEgo
      gear_ok = CS.gearShifter in (car.CarState.GearShifter.drive, car.CarState.GearShifter.unknown) or CS.gearStep > 0

      lead_d = hudControl.leadDistance
      lead_v_rel = hudControl.leadRelSpeed
      lead_dpath = hudControl.leadDPath
      lead_status = (hudControl.leadRadar > 0) or (lead_d > 0.1)

      lead_in_lane = lead_status and abs(lead_dpath) < 1.15 and lead_d > 0.5
      lead_abs_v = v_ego + lead_v_rel
      ttc = (lead_d / max(0.2, abs(lead_v_rel))) if (lead_in_lane and lead_v_rel < -0.3) else 999.0

      a_decel = 3.6 if custom_aeb == 1 else 3.0
      d_min_stop = (v_ego ** 2) / (2.0 * a_decel) + 2.5
      ttc_thresh = 1.8 if custom_aeb == 1 else 2.1

      is_imminent_crash = False
      is_pre_warning = False

      if lead_in_lane and gear_ok:
        # 1. 急剧追尾风险 (TTC过小)
        if ttc < ttc_thresh and lead_d < 45.0 and v_ego > 1.0:
          is_imminent_crash = True
        # 2. 静止车辆/障碍物逼近 (前车停死，自车未减速到安全停距内)
        elif lead_abs_v < 1.2 and lead_d < d_min_stop and v_ego > 1.2:
          is_imminent_crash = True
        # 3. 极端近距碰撞兜底 (< 3.8m 仍在前进)
        elif lead_d < 3.8 and v_ego > 0.8:
          is_imminent_crash = True
        # 预警阈值
        elif ttc < (ttc_thresh + 0.6) or (lead_abs_v < 1.2 and lead_d < d_min_stop + 5.0 and v_ego > 2.0):
          is_pre_warning = True

      # 驾驶员深踩油门避障允许超控 (当 TTC 仍 > 1.2s 时)
      driver_override = CS.gasPressed and (ttc > 1.2) and not (lead_d < 3.0)

      if is_imminent_crash and not driver_override:
        self.aeb_active = True
        self.aeb_hold_frames = int(2.0 / DT_CTRL) # 刹停后防溜保持 2 秒
      elif self.aeb_active:
        # 刹停状态保持逻辑
        if v_ego < 0.3:
          if self.aeb_hold_frames > 0 and not CS.brakePressed:
            self.aeb_hold_frames -= 1
          else:
            self.aeb_active = False
        elif not lead_in_lane or lead_d > 8.0 or lead_v_rel > 1.5:
          self.aeb_active = False

      # 执行制动与动力切断
      if self.aeb_active:
        # 1. 坚决切断巡航油门
        CC.cruiseControl.cancel = True
        # 2. 声光最高优先级报警
        hudControl.visualAlert = car.CarControl.HUDControl.VisualAlert.fcw
        # 3. 标记 AEB 激活
        hudControl.activeCarrot = 9
        # 4. 计算减速度请求 (至少 0.45g，最高 0.85g)
        req_a = max(4.5, (lead_v_rel ** 2) / (2.0 * max(1.0, lead_d - 2.0))) if lead_v_rel < -0.5 else max(4.5, (v_ego ** 2) / (2.0 * max(1.0, lead_d - 2.0)))
        req_a = min(8.3, req_a)
        CC.actuators.accel = -float(req_a)
        if v_ego < 2.5 or lead_d < 5.0:
          CC.actuators.longControlState = car.CarControl.Actuators.LongControlState.stopping
      elif is_pre_warning:
        # 预警阶段：若开着原厂巡航，提前 Cancel 切断油门并发出 FCW 警告
        CC.cruiseControl.cancel = True
        hudControl.visualAlert = car.CarControl.HUDControl.VisualAlert.fcw

    meta = self.sm['modelV2'].meta
    hudControl.modelDesire = 1 if meta.desire == log.Desire.turnLeft else 2 if meta.desire == log.Desire.turnRight else 0

    self._update_side("left",  radarState.leadsLeft2,  meta.distanceToRoadEdgeLeft,  CS.leftBlindspot, hudControl)
    self._update_side("right", radarState.leadsRight2, meta.distanceToRoadEdgeRight, CS.rightBlindspot, hudControl)
    hudControl.rightLaneVisible = True
    hudControl.leftLaneVisible = True

    if self.sm.valid['driverAssistance']:
      hudControl.leftLaneDepart = self.sm['driverAssistance'].leftLaneDeparture
      hudControl.rightLaneDepart = self.sm['driverAssistance'].rightLaneDeparture

    if self.sm['selfdriveState'].active:
      CO = self.sm['carOutput']
      if self.CP.steerControlType == car.CarParams.SteerControlType.angle:
        self.steer_limited_by_controls = abs(CC.actuators.steeringAngleDeg - CO.actuatorsOutput.steeringAngleDeg) > \
                                              STEER_ANGLE_SATURATION_THRESHOLD
      else:
        self.steer_limited_by_controls = abs(CC.actuators.torque - CO.actuatorsOutput.torque) > 1e-2

    dat = messaging.new_message('controlsState')
    dat.valid = CS.canValid
    cs = dat.controlsState
    cs.curvature = self.curvature
    cs.longitudinalPlanMonoTime = self.sm.logMonoTime['longitudinalPlan']
    cs.lateralPlanMonoTime = self.sm.logMonoTime['modelV2']
    cs.desiredCurvature = self.desired_curvature
    cs.longControlState = self.LoC.long_control_state
    cs.upAccelCmd = float(self.LoC.pid.p)
    cs.uiAccelCmd = float(self.LoC.pid.i)
    cs.ufAccelCmd = float(self.LoC.pid.f)
    cs.forceDecel = bool((self.sm['driverMonitoringState'].awarenessStatus < 0. and self.params.get_int("DisableDM") == 0) or
                         (self.sm['selfdriveState'].state == State.softDisabling))

    lat_tuning = self.CP.lateralTuning.which()
    if self.CP.steerControlType == car.CarParams.SteerControlType.angle:
      cs.lateralControlState.angleState = lac_log
    elif lat_tuning == 'pid':
      cs.lateralControlState.pidState = lac_log
    elif lat_tuning == 'torque':
      cs.lateralControlState.torqueState = lac_log

    cs.activeLaneLine = self.lanefull_mode_enabled
    self.pm.send('controlsState', dat)

    cc_send = messaging.new_message('carControl')
    cc_send.valid = CS.canValid
    cc_send.carControl = CC
    self.pm.send('carControl', cc_send)

  def run(self):
    rk = Ratekeeper(100, print_delay_threshold=None)
    while True:
      self.update()
      CC, lac_log = self.state_control()
      self.publish(CC, lac_log)
      rk.monitor_time()

def main():
  config_realtime_process(4, Priority.CTRL_HIGH)
  controls = Controls()
  controls.run()

if __name__ == "__main__":
  main()