#!/usr/bin/env python3
from abc import ABC, abstractmethod

from openpilot.common.realtime import DT_HW
from openpilot.common.numpy_fast import interp
from openpilot.common.swaglog import cloudlog
from openpilot.selfdrive.controls.lib.pid import PIDController

class BaseFanController(ABC):
  @abstractmethod
  def update(self, cur_temp: float, ignition: bool) -> int:
    pass


class TiciFanController(BaseFanController):
  def __init__(self) -> None:
    super().__init__()
    cloudlog.info("Setting up TICI fan handler for Hyundai Custo")

    self.last_ignition = False
    self.controller = PIDController(k_p=0, k_i=4e-3, k_f=1, rate=(1 / DT_HW))

  def update(self, cur_temp: float, ignition: bool) -> int:
    self.controller.neg_limit = -(100 if ignition else 30)
    self.controller.pos_limit = -(30 if ignition else 0)

    if ignition != self.last_ignition:
      self.controller.reset()

    # 库斯途 MPV 智能三段式专属温控策略
    if cur_temp >= 82.0:
      # 极端暴晒段: 强制拉满 100% 极温救险，防止过热死机脱退
      fan_pwr_out = 100 if ignition else 30
    elif cur_temp >= 72.0:
      # 温升过渡段: 72℃~82℃ 线性爬升至 70%
      fan_pwr_out = int(interp(cur_temp, [72.0, 82.0], [30.0, 70.0]))
      if not ignition:
        fan_pwr_out = min(20, fan_pwr_out)
    else:
      # 静音舒适段: < 72℃ 维持在 15%~30% 人耳不敏感区间
      fan_pwr_out = int(interp(cur_temp, [60.0, 72.0], [15.0, 30.0]))
      if not ignition:
        fan_pwr_out = min(15, fan_pwr_out)

    self.last_ignition = ignition
    return fan_pwr_out

