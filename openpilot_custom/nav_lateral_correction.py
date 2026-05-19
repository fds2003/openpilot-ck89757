#!/usr/bin/env python3
import cereal.messaging as messaging
from openpilot.common.realtime import Ratekeeper
import selfdrive.controls.lib.lateral_planner as lp

class NavLateralSafe:
    def __init__(self):
        self.sm = messaging.SubMaster(['navInstruction', 'carState'])
        self.rk = Ratekeeper(100)
        self.last_curv = 0.0

    def run(self):
        print("✅ 导航防提前转弯（安全版）启动")
        while True:
            self.sm.update()
            nav = self.sm.get('navInstruction', None)
            car = self.sm.get('carState', None)

            if not nav or not car:
                self.rk.keep_time()
                continue

            dist_turn = getattr(nav, 'distanceToTurn', 999)
            has_turn = hasattr(nav, 'maneuver') and nav.maneuver in [
                "turnLeft", "turnRight", "laneChangeLeft", "laneChangeRight"
            ]

            # 距离 > 30米 不干预，防止提前打方向
            if not has_turn or dist_turn > 30:
                self.rk.keep_time()
                continue

            # 近路口才轻微修正曲率，不抢控制权
            nav_curv = getattr(nav, 'curvature', 0.0)
            smooth = nav_curv * 0.6 + self.last_curv * 0.4

            if hasattr(lp, 'curvatures') and len(lp.curvatures) > 0:
                lp.curvatures[0] = smooth

            self.last_curv = nav_curv
            self.rk.keep_time()

if __name__ == '__main__':
    n = NavLateralSafe()
    n.run()