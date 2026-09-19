#!/usr/bin/env python3
from cereal import car
from openpilot.common.params import Params
from openpilot.common.realtime import Priority, config_realtime_process
from openpilot.common.swaglog import cloudlog
from openpilot.selfdrive.controls.lib.ldw import LaneDepartureWarning
from openpilot.selfdrive.controls.lib.longitudinal_planner import LongitudinalPlanner
from openpilot.selfdrive.controls.lib.lateral_planner import LateralPlanner
import cereal.messaging as messaging
from openpilot.selfdrive.carrot.carrot_functions import CarrotPlanner


def main():
  config_realtime_process(5, Priority.CTRL_LOW)

  cloudlog.info("plannerd is waiting for CarParams")
  params = Params()
  CP = messaging.log_from_bytes(params.get("CarParams", block=True), car.CarParams)
  cloudlog.info("plannerd got CarParams: %s", CP.brand)

  ldw = LaneDepartureWarning()
  longitudinal_planner = LongitudinalPlanner(CP)
  lateral_planner = LateralPlanner(CP, debug=False)

  pm = messaging.PubMaster(['longitudinalPlan', 'driverAssistance', 'lateralPlan'])
  sm = messaging.SubMaster(['carControl', 'carState', 'controlsState', 'liveParameters', 'radarState', 'modelV2', 'selfdriveState', 'carrotMan'],
                           poll='modelV2', ignore_avg_freq=['radarState'])
  carrot = CarrotPlanner()

  while True:
    sm.update()
    if sm.updated['modelV2']:
      # ① 横向先 update：刷新 lateral_planner.available_road_width（safe_right - safe_left）
      lateral_planner.update(sm, carrot)
      # ② 纵向后 update：读取同一帧的 available_road_width，第⑤重"可用路宽"生效
      longitudinal_planner.update(sm, carrot, lateral_planner=lateral_planner)

      longitudinal_planner.publish(sm, pm, carrot)
      lateral_planner.publish(sm, pm, carrot)

      ldw.update(sm.frame, sm['modelV2'], sm['carState'], sm['carControl'])
      msg = messaging.new_message('driverAssistance')
      msg.valid = sm.all_checks(['carState', 'carControl', 'modelV2', 'liveParameters'])
      msg.driverAssistance.leftLaneDeparture = ldw.left
      msg.driverAssistance.rightLaneDeparture = ldw.right
      pm.send('driverAssistance', msg)


if __name__ == "__main__":
  main()
