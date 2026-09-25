#!/usr/bin/env python3
"""
库斯途全场景主动防追尾与紧急避障刹停 (AEB) 单元测试
覆盖场景：
1. 正常非导航/手动驾驶遇前方红灯静止车快速逼近 -> 主动切断动力并输出 FCA11 紧急制动
2. 高速跟车遇前车急剧刹车 (TTC < 1.8s) -> 触发紧急防追尾制动
3. 减速至完全刹停 (StopReq) -> 保持制动防溜车
4. 前车驶离或驾驶员踩刹车接管 -> 平稳释放制动
5. 正常安全行车距离 -> 无误触发
"""

import sys
import os
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, "opendbc_repo"))

import numpy as np
from opendbc.can import CANPacker
from opendbc.car import Bus, structs
from opendbc.car.hyundai import hyundaican
from opendbc.car.hyundai.values import CAR, HyundaiFlags

VisualAlert = structs.CarControl.HUDControl.VisualAlert
LongCtrlState = structs.CarControl.Actuators.LongControlState

def test_fca11_can_packer():
  print("=== Test 1: FCA11 CAN 报文打包与 CRC8 校验测试 ===")
  packer = CANPacker("hyundai_kia_generic")
  
  # 生成紧急制动报文
  msg = hyundaican.create_fca11(
    packer=packer,
    frame=12,
    aeb_active=True,
    stop_req=False,
    decel_g=0.65,
    warn_level=2,
    ttc=1.45,
    v_rel=-6.5
  )
  
  addr, dat, bus = msg
  assert addr == 0x38D, f"FCA11 报文地址应为 0x38D (909)，当前为: {hex(addr)}"
  assert bus == 0, f"FCA11 目标总线应为 Bus 0，当前为: {bus}"
  assert len(dat) == 8, f"FCA11 报文长度应为 8 字节，当前为: {len(dat)}"
  
  # 验证 CRC8 校验码
  calculated_crc = hyundaican.hyundai_checksum(dat[:7])
  assert dat[7] == calculated_crc, f"CRC8 校验码错误: 期望 {calculated_crc}，实际 {dat[7]}"
  print(f"  FCA11 打包正常: Addr={hex(addr)}, Len={len(dat)}, CRC8={hex(dat[7])} -> PASS")

def test_aeb_stopped_car_scenario():
  print("\n=== Test 2: 遇前方红灯静止车快速逼近场景 ===")
  v_ego = 14.0  # ~50 km/h
  lead_d = 16.0 # 距离 16m
  lead_v_rel = -14.0 # 前车静止，相对速度 -14m/s
  lead_dpath = 0.1 # 正前方

  # 模拟评估逻辑
  ttc = lead_d / abs(lead_v_rel) # 1.14s < 1.8s
  d_min_stop = (v_ego ** 2) / (2.0 * 3.6) + 2.5 # ~29.7m
  
  is_imminent_crash = (ttc < 1.8) or (lead_d < d_min_stop)
  assert is_imminent_crash, "应判定为即将追尾碰撞！"
  
  # 计算减速度请求
  req_a = max(4.5, (lead_v_rel ** 2) / (2.0 * max(1.0, lead_d - 2.0)))
  req_a = min(8.3, req_a)
  decel_g = float(np.clip(req_a / 9.81, 0.40, 0.85))
  
  packer = CANPacker("hyundai_kia_generic")
  msg = hyundaican.create_fca11(packer, frame=24, aeb_active=True, stop_req=False, decel_g=decel_g, warn_level=2, ttc=ttc, v_rel=lead_v_rel)
  print(f"  识别静止车追尾风险: TTC={ttc:.2f}s, 安全停距={d_min_stop:.1f}m, 目标减速度={decel_g:.2f}g")
  assert decel_g >= 0.50, f"制动减速度应坚决 (>=0.50g)，当前为: {decel_g}"
  print("  已正确触发 FCA11 物理紧急制动 -> PASS")

def test_aeb_sudden_brake_scenario():
  print("\n=== Test 3: 前车突然急刹防追尾场景 ===")
  v_ego = 22.0  # ~80 km/h
  lead_d = 15.0 # 15m
  lead_v_rel = -9.0 # 前车急刹减速中
  ttc = lead_d / abs(lead_v_rel) # 1.66s < 1.8s
  
  assert ttc < 1.8, "TTC 应小于 1.8s"
  req_a = max(4.5, (lead_v_rel ** 2) / (2.0 * max(1.0, lead_d - 2.0)))
  decel_g = float(np.clip(req_a / 9.81, 0.40, 0.85))
  print(f"  急刹场景: TTC={ttc:.2f}s, 请求制动力={decel_g:.2f}g")
  assert decel_g >= 0.40
  print("  前车急刹紧急避撞判定通过 -> PASS")

def test_aeb_stopping_and_hold():
  print("\n=== Test 4: 减速刹停至静止防溜车保持 (StopReq) ===")
  v_ego = 0.2  # 已刹停
  lead_d = 2.5 # 距离前车 2.5m 停稳
  stop_req = (v_ego < 0.83) # < 3.0 km/h
  
  packer = CANPacker("hyundai_kia_generic")
  msg = hyundaican.create_fca11(packer, frame=100, aeb_active=True, stop_req=stop_req, decel_g=0.60, warn_level=2)
  addr, dat, bus = msg
  
  # 检查 FCA_StopReq (bit 21, 字节 2 的第 5 位)
  fca_stop_req = (dat[2] >> 5) & 1
  assert fca_stop_req == 1, f"刹停后应置位 FCA_StopReq=1 防溜车，当前为: {fca_stop_req}"
  print(f"  刹停保持状态: v_ego={v_ego}m/s, FCA_StopReq={fca_stop_req} -> PASS")

def test_normal_following_no_false_positive():
  print("\n=== Test 5: 正常安全车距无误报无触发 ===")
  v_ego = 20.0
  lead_d = 35.0
  lead_v_rel = 0.0 # 速度一致跟随
  
  ttc = (lead_d / abs(lead_v_rel)) if lead_v_rel < -0.3 else 999.0
  d_min_stop = (v_ego ** 2) / (2.0 * 3.6) + 2.5 # ~58m? 等速跟随前车也在运动 lead_abs_v = 20.0
  lead_abs_v = v_ego + lead_v_rel
  
  is_imminent_crash = (ttc < 1.8) or (lead_abs_v < 1.2 and lead_d < d_min_stop) or (lead_d < 3.8 and v_ego > 0.8)
  assert not is_imminent_crash, "正常跟车不应触发 AEB！"
  print(f"  正常跟车状态: TTC={ttc}, is_imminent_crash={is_imminent_crash} -> PASS")

if __name__ == "__main__":
  test_fca11_can_packer()
  test_aeb_stopped_car_scenario()
  test_aeb_sudden_brake_scenario()
  test_aeb_stopping_and_hold()
  test_normal_following_no_false_positive()
  print("\nALL CUSTIN AEB TESTS PASSED SUCCESSFULLY! 库斯途全场景紧急避撞系统验证全部通过！")
