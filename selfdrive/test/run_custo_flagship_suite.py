#!/usr/bin/env python3
"""
北京现代库斯途 (Hyundai Custo 2.0T 旗舰版) - 全量自动化测试套件
一键执行阶段一、阶段二、阶段三所有专车深度定制与安全性测试
"""

import importlib.util
import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]

def load_module_from_file(module_name: str, file_path: Path):
  spec = importlib.util.spec_from_file_location(module_name, file_path)
  mod = importlib.util.module_from_spec(spec)
  sys.modules[module_name] = mod
  spec.loader.exec_module(mod)
  return mod

def main():
  suite = unittest.TestSuite()
  loader = unittest.TestLoader()

  # 阶段一：动力学平台参数、NNFF替代映射、interface.py致盲逻辑清理
  stage1_mod = load_module_from_file("test_custo_flagship_stage1", BASE_DIR / "selfdrive" / "car" / "tests" / "test_custo_flagship_stage1.py")
  suite.addTests(loader.loadTestsFromTestCase(stage1_mod.TestCustoFlagshipStage1))

  # 阶段二：智能温控三段式、极温救险保底、非标硬件放行
  stage2_mod = load_module_from_file("test_custo_flagship_stage2", BASE_DIR / "system" / "hardware" / "test_custo_flagship_stage2.py")
  suite.addTests(loader.loadTestsFromTestCase(stage2_mod.TestCustoFlagshipStage2))

  # 阶段三：家庭友好型DM、提示音分级软音化、GPS监控与本地环境隔离
  stage3_mod = load_module_from_file("test_custo_flagship_stage3", BASE_DIR / "selfdrive" / "monitoring" / "tests" / "test_custo_flagship_stage3.py")
  suite.addTests(loader.loadTestsFromTestCase(stage3_mod.TestCustoFlagshipStage3))

  # 阶段四：cp分支优质功能同步 (模型低置信度过滤、开机时区自适应兜底、IPC共享内存残留清理)
  stage4_mod = load_module_from_file("test_cp_optimizations_stage4", BASE_DIR / "selfdrive" / "test" / "test_cp_optimizations_stage4.py")
  suite.addTests(loader.loadTestsFromTestCase(stage4_mod.TestCpOptimizationsStage4))

  runner = unittest.TextTestRunner(verbosity=2)
  result = runner.run(suite)
  sys.exit(not result.wasSuccessful())

if __name__ == "__main__":
  main()
