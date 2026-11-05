#!/usr/bin/env python3
"""
selfdrive/carrot/tests/run_all_tdd_tests.py
=====================================================================
现代库斯途 Comma 3 (cp 分支) —— TDD 全自动化单元测试主运行器
=====================================================================
"""
import sys
import unittest

def main():
  print("=" * 70)
  print("🚗 开始执行【现代库斯途 Comma 3】TDD 驱动验证测试套件...")
  print("=" * 70)

  loader = unittest.TestLoader()
  suite = unittest.TestSuite()

  # 加载核心测试模块
  from test_security_switches import TestSecuritySwitches
  from test_log_rotation import TestLogRotation
  from test_dynamics_invariants import TestDynamicsInvariants
  from test_radard_interlock import TestRadardInterlock
  from test_ttc_and_lane_change_gating import TestTtcAndLaneChangeGating
  from test_cooperative_command_handlers import TestCooperativeCommandHandlers
  from test_atc_state_telemetry import TestAtcStateSettlement
  from test_custin_specs_and_interface import TestCustinSpecsAndInterface
  from test_mpv_smooth_lane_change import TestMpvSmoothLaneChange
  from test_c3_cooperative_modifications import TestC3CooperativeModifications
  from test_amap_navi_networking import TestAmapNaviNetworking
  from test_real_code_contract import TestRealCodeContract
  # F-18~F-22 TDD modules
  from test_f18_front_rear import TestF18FrontRearCopyPaste
  from test_f19_vrel import TestF19VRelConvention
  from test_f20_exp_mode import TestF20ExpModeGating
  from test_f21_print import TestF21PrintToCloudlog
  from test_f22_speed_clamp import TestF22SpeedLimitClamp
  from test_s1_s5_security import (
    TestS1ZmqRce,
    TestS2FtpHardcodedCreds,
    TestS3WebInterfaceCORSAndParams,
    TestS4AmapNaviUdpBinds,
    TestS5CarrotManUdpBinds,
  )
  from test_op_corrections import TestOP01OverpassFilter, TestOP06StoppingBranchDecay

  suite.addTests(loader.loadTestsFromTestCase(TestSecuritySwitches))
  suite.addTests(loader.loadTestsFromTestCase(TestLogRotation))
  suite.addTests(loader.loadTestsFromTestCase(TestDynamicsInvariants))
  suite.addTests(loader.loadTestsFromTestCase(TestRadardInterlock))
  suite.addTests(loader.loadTestsFromTestCase(TestTtcAndLaneChangeGating))
  suite.addTests(loader.loadTestsFromTestCase(TestCooperativeCommandHandlers))
  suite.addTests(loader.loadTestsFromTestCase(TestAtcStateSettlement))
  suite.addTests(loader.loadTestsFromTestCase(TestCustinSpecsAndInterface))
  suite.addTests(loader.loadTestsFromTestCase(TestMpvSmoothLaneChange))
  suite.addTests(loader.loadTestsFromTestCase(TestC3CooperativeModifications))
  suite.addTests(loader.loadTestsFromTestCase(TestAmapNaviNetworking))
  suite.addTests(loader.loadTestsFromTestCase(TestRealCodeContract))
  # F-18~F-22
  suite.addTests(loader.loadTestsFromTestCase(TestF18FrontRearCopyPaste))
  suite.addTests(loader.loadTestsFromTestCase(TestF19VRelConvention))
  suite.addTests(loader.loadTestsFromTestCase(TestF20ExpModeGating))
  suite.addTests(loader.loadTestsFromTestCase(TestF21PrintToCloudlog))
  suite.addTests(loader.loadTestsFromTestCase(TestF22SpeedLimitClamp))
  # S-1~S-5 security RED tests
  suite.addTests(loader.loadTestsFromTestCase(TestS1ZmqRce))
  suite.addTests(loader.loadTestsFromTestCase(TestS2FtpHardcodedCreds))
  suite.addTests(loader.loadTestsFromTestCase(TestS3WebInterfaceCORSAndParams))
  suite.addTests(loader.loadTestsFromTestCase(TestS4AmapNaviUdpBinds))
  suite.addTests(loader.loadTestsFromTestCase(TestS5CarrotManUdpBinds))
  # OP corrections RED tests
  suite.addTests(loader.loadTestsFromTestCase(TestOP01OverpassFilter))
  suite.addTests(loader.loadTestsFromTestCase(TestOP06StoppingBranchDecay))
  runner = unittest.TextTestRunner(verbosity=2)
  result = runner.run(suite)

  print("=" * 70)
  if result.wasSuccessful():
    print(f"🎉 全部 TDD 单元测试通过！(共执行 {result.testsRun} 个断言)")
    print("✅ 状态: GREEN (符合代码重构与生产部署准入标准)")
    print("=" * 70)
    sys.exit(0)
  else:
    print(f"❌ 存在测试失败！失败用例数: {len(result.failures)}, 错误数: {len(result.errors)}")
    print("🛑 状态: RED (禁止部署至车辆，必须修复后方可推进)")
    print("=" * 70)
    sys.exit(1)

if __name__ == "__main__":
  main()
