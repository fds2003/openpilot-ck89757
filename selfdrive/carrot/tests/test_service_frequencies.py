#!/usr/bin/env python3
"""A2 契约测试：amapNavi / carrotMan 服务必须声明真实频率。

frequency 为 0 时 cereal.messaging 不做过期判定，sm.alive 恒真，
C3 会在车机断流后继续消费冻结帧。频率必须与发布线程实发速率一致：
  - amapNavi 由 amap_navi.py 的 Ratekeeper(20) 发布 -> 20Hz
  - carrotMan 由 carrot_serv.py 按 10Hz 周期发布 -> 10Hz

本仓库依赖 capnp，cereal 包无法直接 import，故按文件路径加载纯数据模块。
"""
import importlib.util
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SERVICES_PATH = REPO_ROOT / "cereal" / "services.py"


def _load_services():
  spec = importlib.util.spec_from_file_location("services_under_test", SERVICES_PATH)
  module = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(module)
  return module


services = _load_services()


class TestCooperativeServiceFrequencies(unittest.TestCase):

  def test_amap_navi_declares_20hz(self):
    entry = services._services["amapNavi"]
    self.assertTrue(entry[0], "amapNavi 必须记录进日志")
    self.assertEqual(20., entry[1], "amapNavi 实发 20Hz，声明频率必须一致")

  def test_carrot_man_declares_10hz(self):
    entry = services._services["carrotMan"]
    self.assertTrue(entry[0], "carrotMan 必须记录进日志")
    self.assertEqual(10., entry[1], "carrotMan 周期 10Hz，声明频率必须一致")

  def test_public_service_list_keeps_frequency(self):
    """SERVICE_LIST 由 _services 派生，两侧不得漂移"""
    for name in ("amapNavi", "carrotMan"):
      self.assertEqual(services._services[name][1],
                       services.SERVICE_LIST[name].frequency,
                       f"{name} SERVICE_LIST 与 _services 不一致")
      self.assertGreater(services.SERVICE_LIST[name].frequency, 0.,
                         f"{name} 频率为 0 会让 sm.alive 恒真")


if __name__ == "__main__":
  unittest.main()
