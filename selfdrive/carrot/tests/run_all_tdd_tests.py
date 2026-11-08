#!/usr/bin/env python3
"""
selfdrive/carrot/tests/run_all_tdd_tests.py
=====================================================================
现代库斯途 Comma 3 (cp 分支) —— TDD 全自动化单元测试主运行器
=====================================================================
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

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
  from test_bind_host_contract import TestCarrotBindHost
  from test_lane_postprocess import TestDecode, TestSelectLaneTypes
  from test_lane_image import TestNv12ToRgb, TestInputTensor
  from test_lane_protocol import TestLanePayload
  from test_lane_runtime import TestCheckRuntime, TestDependencyContract
  from test_cooperative_mode import TestHuAlive, TestAutoTurnAllowed, TestWiring as TestCooperativeWiring
  from test_udp_trust import TestSameSubnet, TestEvaluate, TestParseAllowed, TestWiring as TestUdpTrustWiring
  from test_traffic_light import (TestStateFromWire, TestFreshness, TestPrecedence,
                                  TestWiring as TestTrafficLightWiring)
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
  # 19号文档 立即档 Q-4/Q-5/Q-6
  from test_quality_fixes_q4_q5_q6 import (
    TestQ4TurnTypeMapSingleSource,
    TestQ5SpeedHistDeque,
    TestQ6LbRbDrelOwnership,
  )
  # 19号文档 近期档 Q-2/Q-7/Q-8
  from test_quality_fixes_q2_q7_q8 import (
    TestQ2MessageRefactor,
    TestQ7ParseExceptionLayering,
    TestQ8NamingAndEncapsulation,
  )
  # 19号文档 规划档 Q-1（SharedData 读路径锁内快照）
  from test_quality_fix_q1 import (
    TestQ1GoldenValues,
    TestQ1ThreadTearing,
    TestQ1ReadPathLockSnapshot,
  )
  # 19号文档 规划档 Q-3（hasattr 防御调用收敛到统一 capnp 适配层）
  from test_quality_fix_q3 import (
    TestQ3Adapters,
    TestQ3LeadGoldenValues,
    TestQ3CarStateGoldenValues,
    TestQ3HasattrConvergence,
  )

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
  suite.addTests(loader.loadTestsFromTestCase(TestCarrotBindHost))
  # C3 lane_runner (VisionIPC -> lane.onnx -> UDP 4213)
  suite.addTests(loader.loadTestsFromTestCase(TestDecode))
  suite.addTests(loader.loadTestsFromTestCase(TestSelectLaneTypes))
  suite.addTests(loader.loadTestsFromTestCase(TestNv12ToRgb))
  suite.addTests(loader.loadTestsFromTestCase(TestInputTensor))
  suite.addTests(loader.loadTestsFromTestCase(TestLanePayload))
  suite.addTests(loader.loadTestsFromTestCase(TestCheckRuntime))
  suite.addTests(loader.loadTestsFromTestCase(TestDependencyContract))
  suite.addTests(loader.loadTestsFromTestCase(TestHuAlive))
  suite.addTests(loader.loadTestsFromTestCase(TestAutoTurnAllowed))
  suite.addTests(loader.loadTestsFromTestCase(TestCooperativeWiring))
  suite.addTests(loader.loadTestsFromTestCase(TestSameSubnet))
  suite.addTests(loader.loadTestsFromTestCase(TestEvaluate))
  suite.addTests(loader.loadTestsFromTestCase(TestParseAllowed))
  suite.addTests(loader.loadTestsFromTestCase(TestUdpTrustWiring))
  suite.addTests(loader.loadTestsFromTestCase(TestStateFromWire))
  suite.addTests(loader.loadTestsFromTestCase(TestFreshness))
  suite.addTests(loader.loadTestsFromTestCase(TestPrecedence))
  suite.addTests(loader.loadTestsFromTestCase(TestTrafficLightWiring))
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
  # 19号文档 立即档 Q-4/Q-5/Q-6
  suite.addTests(loader.loadTestsFromTestCase(TestQ4TurnTypeMapSingleSource))
  suite.addTests(loader.loadTestsFromTestCase(TestQ5SpeedHistDeque))
  suite.addTests(loader.loadTestsFromTestCase(TestQ6LbRbDrelOwnership))
  # 19号文档 近期档 Q-2/Q-7/Q-8
  suite.addTests(loader.loadTestsFromTestCase(TestQ2MessageRefactor))
  suite.addTests(loader.loadTestsFromTestCase(TestQ7ParseExceptionLayering))
  suite.addTests(loader.loadTestsFromTestCase(TestQ8NamingAndEncapsulation))
  # 19号文档 规划档 Q-1
  suite.addTests(loader.loadTestsFromTestCase(TestQ1GoldenValues))
  suite.addTests(loader.loadTestsFromTestCase(TestQ1ThreadTearing))
  suite.addTests(loader.loadTestsFromTestCase(TestQ1ReadPathLockSnapshot))
  # 19号文档 规划档 Q-3
  suite.addTests(loader.loadTestsFromTestCase(TestQ3Adapters))
  suite.addTests(loader.loadTestsFromTestCase(TestQ3LeadGoldenValues))
  suite.addTests(loader.loadTestsFromTestCase(TestQ3CarStateGoldenValues))
  suite.addTests(loader.loadTestsFromTestCase(TestQ3HasattrConvergence))
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
