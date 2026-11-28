# 20 · 后向雷达门禁与原车 BSM 自动变道阻断方案

> 分支: `cp-custo-amap` ｜ 状态: 代码已完成（TDD GREEN），待实车验证 LCA11 信号 ｜ 前置文档: 02（系统架构）、04（C3 端协同设计）、17（未完成工作）

---

## 1. 背景与问题现象

实车运行中反馈两个问题：

| # | 现象 | 根因 |
| :--- | :--- | :--- |
| P1 | 【盲区有车】提示音每约 2 秒响一次，盲区没车也一直响 | 后向 TTC 门禁 fail-safe 误伤：车辆未安装外接后向雷达时，`amapNavi.lidarBehindVdistTime` 恒为 `0.0` 失效哨兵，触发段被判为"后方有冲突" |
| P2 | 自动变道（ATC / 车机指令 / 自主变道）从不执行 | 同一根因的隐性影响：`rear_conflict` 恒真 → `auto_lane_change_trigger` 每帧被强制置 `False` |

### 1.1 根因链路

```
amap_navi.py (发布端, make_navi_message)
  clear_lane = 无后向目标 AND lidar_l AND lidar_r   # 两侧外接雷达客户端必须同时在线
  ttc = min(ttc_list) if ttc_list else (99.0 if clear_lane else 0.0)
                                    ↑ 无外接雷达时 lidar_l/lidar_r 恒 False → 0.0
desire_helper.py (触发段 TTC 门禁, M-12/M-14)
  rear_conflict = (behind_ttc <= 0.0) or (behind_ttc < ttc_threshold)   # 0.0 → 恒真
  → 每 2 秒 lane_change_audio(True, 6, 0)      # "后方来车"播报 = "盲区有车"音
  → auto_lane_change_trigger = False            # 自动变道被静默永久阻断
```

fail-safe 语义本身正确（传感器失效不得放行变道），但对**未安装该传感器的车辆**缺少配置出口。

---

## 2. 设计方案

### 2.1 新增参数 `RearRadarEnable`（默认 0）

| 值 | 语义 | 行为 |
| :--- | :--- | :--- |
| 0（默认） | 未安装后向雷达 | 触发段：自动变道**默认阻断**（无后方感知不允许盲变），但**不播报**"后方来车"（消除 P1 误报）；驾驶员手动打灯变道不受影响 |
| 1 | 已安装后向雷达 | 恢复完整 fail-safe TTC 门禁：TTC 失效/不足 → 阻断 + 播报；净空（99.0）→ 放行 |

参数读取走 `UnifiedParams`（未注册进 params_keys.h 时安全回退到 `config.py` 默认值），每帧参数刷新块内更新，改参数即时生效。

### 2.2 纯逻辑层 `selfdrive/controls/lib/rear_gate.py`

门禁判定收敛为两个无依赖纯函数（可独立单测，不依赖 cereal/capnp）：

**`evaluate_rear_gate(rear_radar, behind_ttc, overtake_mode, amap_alive) -> (block_auto, play_audio)`**

| 输入 | block_auto | play_audio |
| :--- | :--- | :--- |
| `rear_radar=False`（未装雷达） | `True`（默认不允许自动变道） | `False`（不误报） |
| 已装雷达 + 净空（99.0） | `False` | `False` |
| 已装雷达 + TTC 失效（≤0.0 / 消息缺失） | `True` | `True` |
| 已装雷达 + TTC 不足（< 阈值） | `True` | `True` |

后方 TTC 三档阈值沿用既有语义：OVERTAKE 0=激进 1.8s / 1=标准 2.5s / 2=保守 3.5s，非法档位回退标准档；边界值 `TTC == 阈值` 为放行（`behind_ttc < thr` 才算冲突）。

**`evaluate_bsm_gate(bsm_left, bsm_right, blinker_state, bsm_enabled=True) -> bool`**（原车 BSM 门禁）

| 条件 | 返回 |
| :--- | :--- |
| 变道方向 = 左 且 `carState.leftBlindspot=True` | `True`（阻断自动变道） |
| 变道方向 = 右 且 `carState.rightBlindspot=True` | `True` |
| 对侧有车 / 方向未知（NONE）/ 双闪（BOTH） | `False`（不误伤） |
| `bsm_enabled=False`（`DisableBlindSpot=1`） | `False`（用户已禁用原车盲区信号，永不阻断） |

原车 BSM 信号来自 `LCA11`（CAN 地址 0x58B/1419）的 `CF_Lca_IndLeft/Right`（后视镜盲区指示灯），由 `interface.py:131` 通过 fingerprint 含 `0x58b` 自动启用 `CP.enableBsm` 后由 `carstate.py:351-352` 解析。BSM 门禁为 0/1 开关量、覆盖侧后方角落，**不能替代**后向 TTC 门禁（无距离/速度，无法计算后车逼近碰撞时间），仅作为方向相关的辅助放行/阻断依据。

### 2.3 接线点（`desire_helper.py`）

```
触发段（update() 内，M-12/M-14 门禁原位置）:
  block_auto, play_audio = evaluate_rear_gate(...)   # 后向 TTC / 未装雷达
  block_auto → auto_lane_change_trigger 与 _no_bsd 置 False；play_audio → 每 2 秒播报
  evaluate_bsm_gate(...) → True → auto_lane_change_trigger 置 False   # 仅自动路径

执行段（LaneChangeState.laneChangeStarting, M-15 兜底, 保留原始逻辑不变）:
  驾驶员手动发起: 仅 0.0 < TTC < 阈值 才中止（未装雷达 TTC=0.0 不阻断手动变道）
  自动发起: TTC ≤ 0.0（含未装雷达）一律中止 —— 与"默认不允许自动变道"语义一致
```

注意：BSM 门禁**只**阻断 `auto_lane_change_trigger`，不动 `_no_bsd` 变体与手动扭矩变道路径；执行段兜底保留无条件复检，即使自动变道意外进入 `laneChangeStarting` 也会被 fail-safe 中止。

P0-2 补充：执行段复检的发起方判定收敛为 `rear_gate.is_driver_initiated_change()`——远程车机指令（`trigger_name="cmd"`）**不属于**驾驶员手动变道，归入 fail-safe 严格分支（amapNavi 离线 / TTC≤0.0 一律中止）；复检判定本体为 `rear_gate.evaluate_lane_change_abort()`，两者均有 TDD 覆盖（`test_lane_change_abort_gating.py`）。

### 2.4 未改动部分（既有行为保持）

- 手动变道 BSD 阻断（`desire_helper.py` preLaneChange 的 `blindspot_detected_counter` + `BsdDelayTime`）
- `selfdrived.py` 的 `laneChangeBlocked` 事件与 "Car Detected in Blindspot" 提醒
- 原车 BSM 手动变道防护、转弯（ATC turn）流程
- `DisableBlindSpot` 原语义（禁用原车盲区信号参与手动变道判定）

---

## 3. TDD 记录

开发顺序严格遵循 RED → GREEN → 回归，生产代码先于实现被测试定义：

| 步骤 | 内容 | 结果 |
| :--- | :--- | :--- |
| RED-1 | `test_rear_radar_gating.py`（8 用例）先行，运行报 `ModuleNotFoundError` | FAILED（RED） |
| GREEN-1 | 实现 `rear_gate.evaluate_rear_gate` + `desire_helper` 接线 | 8/8 + 既有 4/4 通过 |
| RED-2 | `test_bsm_lane_change_gating.py`（6 用例）先行 | FAILED（RED） |
| GREEN-2 | 实现 `evaluate_bsm_gate` + 接线 | 18/18 通过 |

测试覆盖：无雷达静默阻断 + 消音、净空放行、TTC 失效/负值/消息缺失 fail-safe、三档阈值、边界值（TTC==thr 放行）、非法档位回退、BSM 方向相关性、对侧不误伤、DisableBlindSpot 豁免、未知方向不阻断。

```bash
# 测试运行方式（仓库根目录）
PYTHONPATH=$PWD python3 -m unittest \
  selfdrive.carrot.tests.test_rear_radar_gating \
  selfdrive.carrot.tests.test_bsm_lane_change_gating \
  selfdrive.carrot.tests.test_ttc_and_lane_change_gating
```

既有 `test_ttc_and_lane_change_gating.py` 的 `evaluate_rear_conflict`（独立副本）逻辑未改动，作为回归基线继续通过。

---

## 4. 参数与设置入口

| 参数 | 默认 | 说明 | 入口 |
| :--- | :--- | :--- | :--- |
| `RearRadarEnable` | 0 | 1=已安装后向雷达（启用后方 TTC 门禁与播报）；0=未安装（默认不允许自动变道，不播报） | Carrot Web 设置 → 公共参数设置 → "后向雷达已安装"；HTTP 8088 白名单已含 |
| `DisableBlindSpot` | 0 | 1=禁用原车盲区信号参与判定（同时豁免 BSM 门禁） | 既有入口 |
| `LaneChangeBsd` | 0 | -1=忽略 BSD 盲区检测（仅影响手动变道阻止路径） | 既有入口 |

## 5. 实车验证方案（LCA11 信号）

验证工具：`selfdrive/carrot/verify_bsm.py`（设备 onroad 状态下运行）。

```bash
cd /data/openpilot
python3 selfdrive/carrot/verify_bsm.py --can
```

脚本输出：`carFingerprint` / `enableBsm` / fingerprint 是否含 0x58B；实时 `L:●有车/ 无车` 状态变化事件（带时间戳与转向灯状态）；`--can` 模式统计并采样打印 0x58B 原始帧。

**步骤清单**（约 5 分钟）：

1. 启动脚本：期望 `enableBsm: True`、`fingerprint 含 0x58B: True`
2. 侧后方无车：期望 `L: 无车  R: 无车`
3. 旁边车道有车并行/驶过（后视镜灯亮）：期望对应侧 `●有车`，与灯同步
4. 打左/右转向灯：输出尾部 `blinker L:1 / R:1`
5. `--can` 采样：`[can] 0x58B bus=0 data=...` 帧数持续增长

**判定矩阵**：

| 现象 | 结论 | 处理 |
| :--- | :--- | :--- |
| `enableBsm=False` 且无 0x58B 帧 | 车辆未发 LCA11（低配无 BSM 或报文不在 bus0） | 抓全总线帧地址排查 |
| `enableBsm=False` 但有 0x58B 帧 | fingerprinting 未收录该地址 | 补充 fingerprint 匹配规则 |
| `enableBsm=True`、灯亮但 L/R 恒 0 | 信号字节解析问题 | 将 `--can` 抓取的 data 对照 DBC 核对字节位 |
| 全部正常 | BSM 门禁链路打通 | 收工 |

交叉验证：`ShowDebugLog=4` 时驾驶日志出现 `blindspot=...,L:x,R:x`（desire_helper 状态打印）。

---

## 6. 部署与回滚

- **部署**：设备拉取本分支后重启 manager 即可生效；`RearRadarEnable` 默认 0，无需改参数（无雷达用户开箱即正确）
- **改装雷达后**：设置 `RearRadarEnable=1`，恢复完整 TTC 门禁与自动变道
- **回滚**：revert 本次提交即可，无数据/参数迁移（`RearRadarEnable` 未注册进 C++ params_keys，删除代码后残留参数值无副作用）

## 7. 变更文件清单

| 文件 | 变更 |
| :--- | :--- |
| `selfdrive/controls/lib/rear_gate.py` | 新增：`evaluate_rear_gate` / `evaluate_bsm_gate` 纯逻辑 + BLINKER_* 常量 |
| `selfdrive/controls/lib/desire_helper.py` | 触发段接线两处门禁；`rear_radar` 参数读取；执行段兜底保留 |
| `selfdrive/carrot/config.py` | `RearRadarEnable` 默认值 0 |
| `selfdrive/carrot/nav_params.html` | Web 设置页新增"后向雷达已安装"开关 |
| `selfdrive/carrot/web_interface.py` | HTTP 8088 参数白名单加入 `RearRadarEnable` |
| `selfdrive/carrot/tests/test_rear_radar_gating.py` | 新增：rear gate 8 用例 |
| `selfdrive/carrot/tests/test_bsm_lane_change_gating.py` | 新增：BSM gate 6 用例 |
| `selfdrive/carrot/verify_bsm.py` | 新增：LCA11 实车验证脚本 |
| `docs/custin/README.md` | 文档索引登记本篇（20 号） |
