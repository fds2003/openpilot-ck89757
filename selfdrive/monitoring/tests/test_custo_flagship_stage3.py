#!/usr/bin/env python3
"""
北京现代库斯途 (Hyundai Custo 2.0T 旗舰版) - 阶段三单元测试
验证：
1. selfdrive/monitoring/helpers.py 纯洁性（彻底移除借用斯巴鲁参数与重复逻辑）与 MPV 家庭级偏头/闭眼容限
2. selfdrive/ui/soundd.py 库斯途音量分级控制（Quiet Drive 联动 35% 微音、紧急接管 70% 保底、CustoDMVolumeRatio 参数）
3. selfdrive/controls/controlsd.py GPS 监控逻辑恢复（出地库 1500m 后惯导失效恢复报 EventName.noGps）
4. launch_env.sh 本地配置隔离与 launch_env.local.template 模板
"""

import os
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[3]

class TestCustoFlagshipStage3(unittest.TestCase):

  def test_helpers_pure_and_tolerances(self):
    helpers_path = BASE_DIR / "selfdrive" / "monitoring" / "helpers.py"
    self.assertTrue(helpers_path.exists(), f"helpers.py not found at {helpers_path}")
    content = helpers_path.read_text(encoding="utf-8")

    # 1. 纯洁性验证：彻底移除借用斯巴鲁开关及 Params 引入
    self.assertNotIn("SubaruManualParkingBrakeSng", content, "helpers.py still contains SubaruManualParkingBrakeSng!")
    self.assertNotIn("from openpilot.common.params import Params", content, "helpers.py still imports Params directly!")
    self.assertNotIn("def dm_open", content, "helpers.py still contains duplicate dm_open function!")
    self.assertNotIn("def dm_close", content, "helpers.py still contains duplicate dm_close function!")

    # 2. 库斯途专车家庭友好型容限常数验证
    self.assertIn("self._DISTRACTED_TIME = 16.", content, "库斯途偏头容限未设为 16s")
    self.assertIn("self._BLINK_THRESHOLD = 0.865", content, "库斯途闭眼阈值未严守 0.865")
    self.assertIn("self._POSE_YAW_THRESHOLD_SLACK = 0.55", content, "库斯途偏航角容限未设为 0.55")

  def test_soundd_custo_volume_control(self):
    soundd_path = BASE_DIR / "selfdrive" / "ui" / "soundd.py"
    self.assertTrue(soundd_path.exists(), f"soundd.py not found at {soundd_path}")
    content = soundd_path.read_text(encoding="utf-8")

    # 1. 验证 Quiet Drive 🤫 联动与 CustoDMVolumeRatio 逻辑
    self.assertIn("QuietDrive", content, "soundd.py 未包含 QuietDrive 联动判断")
    self.assertIn("CustoDMVolumeRatio", content, "soundd.py 未支持 CustoDMVolumeRatio 自定义参数")
    self.assertIn("0.35", content, "soundd.py QuietDrive 开启时默认微音比例不是 0.35")

    # 2. 验证音量分级与紧急接管保底逻辑
    self.assertIn("AudibleAlert.warningImmediate", content, "soundd.py 未对 warningImmediate 做音量分级处理")
    self.assertIn("max(0.7, self.dm_volume_ratio)", content, "soundd.py 紧急接管声音未设置 70% 最低保底音量")

  def test_controlsd_gps_event_restored(self):
    controlsd_path = BASE_DIR / "selfdrive" / "controls" / "controlsd.py"
    self.assertTrue(controlsd_path.exists(), f"controlsd.py not found at {controlsd_path}")
    content = controlsd_path.read_text(encoding="utf-8")

    # 验证 self.events.add(EventName.noGps) 是否已取消注释
    self.assertIn("if not self.sm['liveLocationKalman'].gpsOK and self.sm['liveLocationKalman'].inputsOK and (self.distance_traveled > 1500):", content)
    self.assertIn("self.events.add(EventName.noGps)", content, "controlsd.py 中 EventName.noGps 仍被注释或缺失")
    self.assertNotIn("#self.events.add(EventName.noGps)", content, "controlsd.py 中仍存在被注释的 #self.events.add(EventName.noGps)")

  def test_launch_env_and_local_template(self):
    launch_env_path = BASE_DIR / "launch_env.sh"
    template_path = BASE_DIR / "launch_env.local.template"
    gitignore_path = BASE_DIR / ".gitignore"

    self.assertTrue(launch_env_path.exists())
    self.assertTrue(template_path.exists())
    self.assertTrue(gitignore_path.exists())

    launch_content = launch_env_path.read_text(encoding="utf-8")
    self.assertIn("launch_env.local", launch_content, "launch_env.sh 未包含加载 launch_env.local 的逻辑")

    gitignore_content = gitignore_path.read_text(encoding="utf-8")
    self.assertIn("launch_env.local", gitignore_content, ".gitignore 未忽略 launch_env.local")

    template_content = template_path.read_text(encoding="utf-8")
    self.assertIn("CUSTO_DM_VOLUME_RATIO", template_content, "launch_env.local.template 缺少 CUSTO_DM_VOLUME_RATIO 配置项")

if __name__ == "__main__":
  unittest.main()
