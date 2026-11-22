#!/usr/bin/env python3
"""
北京现代库斯途 (Hyundai Custo 2.0T 旗舰版) - 阶段四 (cp 分支优质功能同步) TDD 单元测试
测试内容：
1. test_model_noise_filter: 视觉模型输出噪声置信度切除 (lane_lines <= 0.2 归零, lead <= 0.35 归零, >门限保持, 缺key防御)
2. test_timezone_fallback_script: launch_env.sh 时区自动化兜底 (包含 Asia/Shanghai、[ -d "/data/etc" ] 目录守护与容错)
3. test_shm_patch_cleanup: 共享内存与信号量生命周期隔离 (白名单精准清除 cereal./openpilot./sem.cereal, 绝不误删其他系统文件, 跨平台安全)
4. test_manager_integration: manager.py 中是否已正确集成 cleanup_shared_memory_on_start
"""

import os
import sys
import unittest
import tempfile
from pathlib import Path
import numpy as np

BASE_DIR = Path(__file__).resolve().parents[2]
if str(BASE_DIR) not in sys.path:
  sys.path.insert(0, str(BASE_DIR))

# 适配 Windows 测试环境下缺失的符号链接包映射
try:
  import openpilot.selfdrive.modeld
except ImportError:
  import selfdrive
  import selfdrive.modeld
  sys.modules["openpilot.selfdrive"] = selfdrive
  sys.modules["openpilot.selfdrive.modeld"] = selfdrive.modeld

from selfdrive.modeld.parse_model_outputs import Parser


class TestCpOptimizationsStage4(unittest.TestCase):

  def test_model_noise_filter_boundary_and_cutting(self):
    """验证模型输出低置信度门限切除 (车道线 <=0.2 归零, 前车 <=0.35 归零)"""
    parser = Parser(ignore_missing=True)

    # 1. 构造包含边界值与典型值的测试用例
    # 注意: parse_outputs 内部对 lane_lines_prob 和 lead_prob 做 sigmoid 转换:
    # prob = sigmoid(logit) => logit = ln(p / (1 - p))
    lane_probs_target = np.array([0.05, 0.199, 0.200, 0.201, 0.850])
    lane_logits = np.log(lane_probs_target / (1.0 - lane_probs_target))

    lead_probs_target = np.array([0.10, 0.349, 0.350, 0.351, 0.950])
    lead_logits = np.log(lead_probs_target / (1.0 - lead_probs_target))

    outs = {
      'lane_lines_prob': lane_logits,
      'lead_prob': lead_logits,
      'meta': np.zeros(1),
      'desire_state': np.zeros((1, 8)),
      'desire_pred': np.zeros((1, 4, 8)),
    }

    # 执行解析与过滤
    parser.parse_outputs(outs)

    # 2. 断言车道线门限切除 (0.2 边界)
    self.assertEqual(outs['lane_lines_prob'][0], 0.0, "0.05 车道线噪点未被置 0")
    self.assertEqual(outs['lane_lines_prob'][1], 0.0, "0.199 车道线噪点未被置 0")
    self.assertEqual(outs['lane_lines_prob'][2], 0.0, "0.200 临界车道线未被置 0")
    self.assertAlmostEqual(outs['lane_lines_prob'][3], 0.201, places=3, msg="0.201 有效应保留")
    self.assertAlmostEqual(outs['lane_lines_prob'][4], 0.850, places=3, msg="0.850 强信号应保留")

    # 3. 断言前车门限切除 (0.35 边界)
    self.assertEqual(outs['lead_prob'][0], 0.0, "0.10 幽灵前车噪点未被置 0")
    self.assertEqual(outs['lead_prob'][1], 0.0, "0.349 幽灵前车噪点未被置 0")
    self.assertEqual(outs['lead_prob'][2], 0.0, "0.350 临界前车未被置 0")
    self.assertAlmostEqual(outs['lead_prob'][3], 0.351, places=3, msg="0.351 有效前车应保留")
    self.assertAlmostEqual(outs['lead_prob'][4], 0.950, places=3, msg="0.950 强信号前车应保留")

  def test_model_noise_filter_missing_key_robustness(self):
    """验证当输入缺少 lane_lines_prob 或 lead_prob 时系统健壮不崩溃"""
    parser = Parser(ignore_missing=True)
    outs = {
      'meta': np.zeros(1),
      'desire_state': np.zeros((1, 8)),
      'desire_pred': np.zeros((1, 4, 8)),
    }
    # 不应抛出 KeyError
    try:
      parser.parse_outputs(outs)
    except KeyError as e:
      self.fail(f"parse_outputs 在缺失 key 时抛出了 KeyError: {e}")

  def test_timezone_fallback_script(self):
    """验证 launch_env.sh 中的时区兜底脚本与防御守护"""
    launch_env_path = BASE_DIR / "launch_env.sh"
    self.assertTrue(launch_env_path.exists())
    content = launch_env_path.read_text(encoding="utf-8")

    self.assertIn("Asia/Shanghai", content, "未配置 Asia/Shanghai 东八区时区")
    self.assertIn('/data/etc/localtime', content, "未探测 /data/etc/localtime")
    self.assertIn('[ -d "/data/etc" ]', content, "未包含 /data/etc 真实硬件目录守护")

  def test_shm_patch_cleanup_logic(self):
    """TDD 测试: 验证共享内存清理模块的前缀白名单机制与隔离安全"""
    patch_path = BASE_DIR / "system" / "manager" / "manager_shm_patch.py"
    self.assertTrue(patch_path.exists(), f"manager_shm_patch.py 必须存在于 {patch_path}")

    # 动态加载补丁模块
    import importlib.util
    spec = importlib.util.spec_from_file_location("manager_shm_patch", patch_path)
    shm_patch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(shm_patch)

    # 在临时目录模拟 /dev/shm 环境
    with tempfile.TemporaryDirectory() as tmp_shm:
      # 创建白名单目标文件
      cereal_seg = Path(tmp_shm) / "cereal.controlsState"
      openpilot_seg = Path(tmp_shm) / "openpilot.ui"
      sem_seg = Path(tmp_shm) / "sem.cereal.0"

      # 创建系统其他程序非目标文件 (绝不能误删)
      systemd_file = Path(tmp_shm) / "systemd.lock"
      pulse_file = Path(tmp_shm) / "pulse-shm-1234"

      for f in (cereal_seg, openpilot_seg, sem_seg, systemd_file, pulse_file):
        f.write_text("test_data")

      # 临时替换补丁的 _SHM_DIR 进行精准测试
      old_shm_dir = shm_patch._SHM_DIR
      shm_patch._SHM_DIR = tmp_shm
      try:
        removed = shm_patch._cleanup_shm()
        self.assertEqual(removed, 3, f"应该精准清理 3 个 openpilot/cereal 段，实际清理: {removed}")

        # 断言目标文件已被删除
        self.assertFalse(cereal_seg.exists(), "cereal.controlsState 未被清理")
        self.assertFalse(openpilot_seg.exists(), "openpilot.ui 未被清理")
        self.assertFalse(sem_seg.exists(), "sem.cereal.0 未被清理")

        # 断言系统非目标文件毫发无损
        self.assertTrue(systemd_file.exists(), "系统非目标文件 systemd.lock 被错误删除！")
        self.assertTrue(pulse_file.exists(), "系统非目标文件 pulse-shm-1234 被错误删除！")
      finally:
        shm_patch._SHM_DIR = old_shm_dir

  def test_manager_integration(self):
    """验证 manager.py 中是否已集成 cleanup_shared_memory_on_start"""
    manager_path = BASE_DIR / "system" / "manager" / "manager.py"
    self.assertTrue(manager_path.exists())
    content = manager_path.read_text(encoding="utf-8")

    self.assertIn("cleanup_shared_memory_on_start", content, "manager.py 未集成 cleanup_shared_memory_on_start")


if __name__ == "__main__":
  unittest.main()
