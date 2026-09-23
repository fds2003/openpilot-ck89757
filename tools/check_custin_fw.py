#!/usr/bin/env python3
"""
check_custin_fw.py — 库斯途(Custin) 固件指纹自检工具

用法（在 comma 设备上跑）:
    cd /data/openpilot
    python3 tools/check_custin_fw.py

它会:
  1. 读出设备缓存的 CarParams（含车上的真实固件版本号）
  2. 打印实际识别到的车型 / 匹配来源 / 是否模糊匹配
  3. 用 opendbc 自己的正则解析出每个 ECU 的 platform code
  4. 和库里 HYUNDAI_CUSTIN_1ST_GEN 期望的代码逐条比对，给出结论

如果识别结果不是 Custin，把本脚本的输出贴出来即可判断差在哪。
"""

import sys

from cereal import car
from opendbc.car.hyundai.values import CAR, PLATFORM_CODE_ECUS, DATE_FW_ECUS, get_platform_codes
from opendbc.car.hyundai.fingerprints import FW_VERSIONS
from opendbc.car.structs import CarParams
from openpilot.common.params import Params

Ecu = CarParams.Ecu
CUSTIN = CAR.HYUNDAI_CUSTIN_1ST_GEN

# 这些 ECU 参与 platform code 匹配（见 hyundai/values.py: PLATFORM_CODE_ECUS）
ADDR_TO_NAME = {
    0x7d0: "fwdRadar",
    0x7d1: "abs",
    0x7d4: "eps",
    0x7c4: "fwdCamera",
}


def fmt_code(codes):
    if not codes:
        return "(无)"
    out = []
    for code, date in sorted(codes):
        out.append(f"{code.decode(errors='replace')}" + (f" @{date.decode()}" if date else ""))
    return ", ".join(out)


def main():
    CP = None
    try:
        raw = Params().get("CarParams")
        if raw:
            CP = car.CarParams.from_bytes(raw)
    except Exception as e:
        print(f"[!] 读取 CarParams 失败: {type(e).__name__}: {e}")

    if CP is None:
        print("[!] 设备里没有缓存的 CarParams。")
        print("    请先在车上让 openpilot 完成一次指纹识别（上车、车辆处于原厂模式、")
        print("    保持 30s 以上），然后再跑本脚本。")
        return 1

    print("=" * 62)
    print("一、设备当前识别结果")
    print("=" * 62)
    print(f"  车型 (carFingerprint) : {CP.carFingerprint}")
    print(f"  品牌                  : {CP.brand}")
    print(f"  匹配来源              : {CP.fingerprintSource}")
    print(f"  是否模糊匹配          : {bool(CP.fuzzyFingerprint)}")
    print(f"  VIN                   : {CP.carVin or '(空)'}")
    print(f"  转向类型              : {CP.steerControlType}")

    is_custin = CP.carFingerprint == str(CUSTIN)
    print()
    if is_custin:
        print("  ✅ 已识别为 Hyundai Custin 1st Gen —— 指纹匹配通过")
    elif CP.carFingerprint == "MOCK":
        print("  ❌ 未匹配任何车型（回落成 MOCK）—— 需要用下面的信息补指纹")
    else:
        print(f"  ⚠️  识别成了其它车型，不是 Custin —— 需要核对指纹")

    # ---- 打印车上真实固件 ----
    print()
    print("=" * 62)
    print("二、车上读到的固件版本（关键 ECU）")
    print("=" * 62)
    live = {}
    for fw in CP.carFw:
        if not fw.logging:
            live.setdefault(fw.address, []).append(bytes(fw.fwVersion))

    if not live:
        print("  [!] CarParams 里没有 carFw 数据（可能是缓存太旧或未做 FW 查询）")

    for addr in (0x7c4, 0x7d0, 0x7d4, 0x7d1):
        name = ADDR_TO_NAME.get(addr, "?")
        vers = live.get(addr, [])
        if not vers:
            print(f"  [{name} 0x{addr:x}] (未读到)")
            continue
        for v in vers:
            print(f"  [{name} 0x{addr:x}] {v!r}")

    # ---- platform code 比对 ----
    print()
    print("=" * 62)
    print("三、Platform Code 比对（决定模糊匹配成败的关键）")
    print("=" * 62)
    expected_fws = FW_VERSIONS.get(CUSTIN, {})

    all_ok = True
    for ecu in PLATFORM_CODE_ECUS:
        # 找到该 ECU 在期望表里的地址
        exp_addr = None
        for (e, a, _s), _v in expected_fws.items():
            if e == ecu:
                exp_addr = a
                break
        if exp_addr is None:
            continue

        exp_versions = [v for (e, a, _s), vs in expected_fws.items() if e == ecu and a == exp_addr for v in vs]
        exp_codes = {c for c, _ in get_platform_codes(exp_versions)}
        exp_dates = {d for _, d in get_platform_codes(exp_versions) if d is not None}

        found_codes = {c for c, _ in get_platform_codes(live.get(exp_addr, []))}
        found_dates = {d for _, d in get_platform_codes(live.get(exp_addr, [])) if d is not None}

        code_hit = bool(found_codes & exp_codes)
        date_ok = True
        if ecu in DATE_FW_ECUS:
            date_ok = bool(exp_dates) and bool(found_dates) and \
                      any(min(exp_dates) <= d <= max(exp_dates) for d in found_dates)

        ok = code_hit and date_ok
        all_ok &= ok

        print(f"  [{ADDR_TO_NAME.get(exp_addr, ecu)} 0x{exp_addr:x}] {'✅' if ok else '❌'}")
        print(f"      期望 code : {fmt_code(exp_codes)}")
        print(f"      车上 code : {fmt_code(found_codes)}")
        if ecu in DATE_FW_ECUS:
            print(f"      期望日期  : {', '.join(d.decode() for d in sorted(exp_dates)) or '(无)'}")
            print(f"      车上日期  : {', '.join(d.decode() for d in sorted(found_dates)) or '(无)'}")
        print(f"      code命中={code_hit}  日期通过={date_ok}")

    print()
    print("=" * 62)
    print("四、结论")
    print("=" * 62)
    if is_custin:
        print("  ✅ 车型识别正常，无需补指纹。可以进入下一步（横向标定）。")
    elif all_ok:
        print("  ⚠️  platform code 全部命中，但最终识别成了别的车型。")
        print("     多半是多个候选车同时命中（歧义），需要人工指定或用 CarSelected3 手动选车。")
    else:
        print("  ❌ 有关键 ECU 的 platform code 没命中 —— 这是识别失败的原因。")
        print("     解法二选一：")
        print("       A) 把上面『车上 code / 车上日期』补进")
        print("          opendbc/car/hyundai/fingerprints.py 的 HYUNDAI_CUSTIN_1ST_GEN 条目")
        print("       B) 用 UI 的『选择您的车辆』手动指定 Hyundai Custin 2023（走 CarSelected3 后门）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
