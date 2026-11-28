#!/usr/bin/env python3
"""实车验证 Custin 原车 BSM (LCA11, 0x58B) 盲区信号接入。

设备上运行（onroad 状态）:
  cd /data/openpilot
  python3 selfdrive/carrot/verify_bsm.py            # 监控 carState 盲区信号
  python3 selfdrive/carrot/verify_bsm.py --can      # 额外统计 LCA11 原始 CAN 帧

验证步骤:
  1. 上车前先看脚本输出 carFingerprint / enableBsm（enableBsm 必须为 True）
  2. 打左/右转向灯，侧后方无车 → 期望 L:0 R:0
  3. 旁边车道有车并行/驶过（后视镜灯亮）→ 期望对应侧 L:1 / R:1，与后视镜灯一致
  4. --can 模式下 0x58B 帧计数应持续增长（证明角落雷达在发报文）

判定:
  - enableBsm=False 且 --can 无 0x58B 帧 → 车辆未发 LCA11（配置或总线问题）
  - enableBsm=False 但 --can 有 0x58B 帧 → fingerprint 未包含该地址，检查 fingerprinting
  - enableBsm=True 但 L:R 恒 0 且后视镜灯亮 → 信号字节解析问题，用 --can 抓原始帧对比
"""
import argparse
import time

from cereal import messaging

LCA11_ADDR = 0x58B  # 1419, LCA11: CF_Lca_IndLeft / CF_Lca_IndRight


def main():
  parser = argparse.ArgumentParser(description="Custin BSM (LCA11) 实车验证")
  parser.add_argument("--can", action="store_true", help="同时统计 LCA11 原始 CAN 帧")
  args = parser.parse_args()

  services = ['carState', 'carParams']
  if args.can:
    services.append('can')
  sm = messaging.SubMaster(services)

  print("等待消息... (设备需处于 onroad 状态)")
  frame = 0
  last_l = last_r = None
  can_frames = 0          # 0x58B 帧计数
  last_bus = None
  params_printed = False

  while True:
    sm.update(100)
    frame += 1

    # 打印一次车辆指纹与 enableBsm
    if not params_printed and sm.updated['carParams']:
      cp = sm['carParams']
      print(f"\n=== carParams ===")
      print(f"carFingerprint : {cp.carFingerprint}")
      print(f"enableBsm      : {cp.enableBsm}")
      print(f"启动时见到的 fingerprint (bus0) 含 0x58B: {LCA11_ADDR in cp.fingerprint[0] if len(cp.fingerprint) > 0 else 'N/A'}")
      if not cp.enableBsm:
        print("!! enableBsm=False: carState.leftBlindspot 将恒为 False（见文首判定表）")
      print(f"\n=== 实时盲区信号 (Ctrl+C 退出) ===")
      params_printed = True

    if not sm.updated['carState']:
      continue

    cs = sm['carState']
    l, r = bool(cs.leftBlindspot), bool(cs.rightBlindspot)

    # 原始 CAN 统计
    if args.can and sm.updated['can']:
      for can in sm['can']:
        if can.address == LCA11_ADDR:
          can_frames += 1
          last_bus = can.src
          if can_frames % 50 == 1:  # 采样打印原始帧
            print(f"  [can] 0x{LCA11_ADDR:X} bus={can.src} data={can.dat.hex()}")

    # 状态变化时打印事件（便于与后视镜灯对照）
    if (l, r) != (last_l, last_r):
      ts = time.strftime('%H:%M:%S')
      state = lambda v: "●有车" if v else " 无车"
      print(f"[{ts}] L:{state(l)}  R:{state(r)}  "
            f"(blinker L:{int(cs.leftBlinker)} R:{int(cs.rightBlinker)})"
            + (f"  [0x58B帧数={can_frames}, bus={last_bus}]" if args.can else ""))
      last_l, last_r = l, r

    # 每 10 秒心跳，确认链路活着
    if frame % 100 == 0:
      tail = f"  [0x58B帧数={can_frames}, bus={last_bus}]" if args.can else ""
      print(f"... {time.strftime('%H:%M:%S')} L:{int(l)} R:{int(r)}{tail}")


if __name__ == "__main__":
  try:
    main()
  except KeyboardInterrupt:
    print("\n结束")
