# Code Review 修复清单

> 审查范围：`origin/cp...HEAD`（merge-base `24b7ff2`，17 提交，45 文件，+3940/-100）
> 生成时间：2026-11-04
> 两轴：Standards（标准）/ Spec（需求）。P0 = 安全需求或 lint 红线，P1 = 正确性，P2 = 质量/卫生。

## P0 — 安全需求未达成 / lint 红线

- [x] **P0-1 (Spec) CANCEL 无法在 50ms 内中止变道**（已修复，TDD GREEN：test_cancel_priority.py 契约测试）
  - 位置：`selfdrive/controls/lib/desire_helper.py:497,526,523,1319-1324`
  - 问题：CANCEL 分支是 `if carrot_lane_change_count > 0` 之后的 `elif`；OVERTAKE 将计数置 400 帧（20s），CANCEL 要等 `laneChangeFinishing` 重置后才被消费。
  - 需求：README「CANCEL 指令 50ms 内立即中止变道」/ COOPERATIVE_PILOT.md:88。
  - 修复：CANCEL 消费提到计数判断之前（独立 if 分支，优先级最高）；补一条端到端时序测试。
  - 落地：CANCEL 分支提升为链首独立 if（desire_helper.py:501-514）；跨端核对确认车机断联自动 CANCEL ×3 同 seq、C3 去重仅首包有效，重发无法补救——本修复使首包即被消费。

- [x] **P0-2 (Spec) 远程指令变道未走 fail-safe TTC 中止**（已修复，TDD GREEN：test_lane_change_abort_gating.py 13 用例）
  - 位置：`desire_helper.py:1159-1163, 1258`
  - 问题：`trigger_type == 3` 同时覆盖 `trigger_name == "cmd"`（远程），`is_driver_initiated` 误判为 True，使用宽松 abort 条件 `0.0 < _ttc < _thr`；amapNavi 死亡或 ttc=0.0 时反而不中止。
  - 需求：39ded308 "decouple driver vs remote TTC abort"；98e0f4df "amapNavi dead -> behind_ttc=0.0 -> fail-safe block"。
  - 修复：`is_driver_initiated` 排除 `trigger_name == "cmd"`；ttc=0.0 视为未确认清空 → 中止。
  - 落地：rear_gate.py 新增 `is_driver_initiated_change()` / `evaluate_lane_change_abort()` 纯函数，desire_helper.py 执行段复检改为调用；cmd 变道归入 fail-safe 严格分支。

- [x] **P0-3 (Spec) echo_cmd UI 开关缺失，功能永久死路**（已修复，TDD GREEN：test_echo_cmd_switch.py 4 用例契约测试）
  - 位置：`common/params_keys.h`、`selfdrive/carrot/nav_params.html`、`carrot_man.py:882-886`
  - 问题：`CarrotEchoCmdEnable` 未注册 → `UnifiedParams.get_bool` 恒 `default=False`；`test_security_switches.py` 用 `MockParams` 测不出。
  - 需求：39ded308 "secure echo_cmd gateway with **UI switch** and 423 lockout"。
  - 修复：注册 key + HTML 开关 + 默认值确认；测试改用真实 Params（或 OpenpilotPrefix 沙箱）。
  - 落地：params_keys.h 注册 `{"CarrotEchoCmdEnable", PERSISTENT}`（nav_params 页保存路径经 UnifiedParams._save_system_param 依赖此注册）；config.py 默认 0；nav_params.html 新增开关（公共参数设置组）；carrot_settings.json / apilot.json 清单补条目。静态契约测试替代 MockParams（设备 .so 环境限制），写入路径语义经 config.py:74 核实。

- [x] **P0-4 (Spec) amapNavi stale 时的 legacy BSD fallback 被回退**（已修复，TDD GREEN：test_rear_radar_gating / test_lane_change_abort_gating 扩展 13 用例）
  - 位置：`selfdrive/carrot/amap_navi.py:311-315`、`desire_helper.py:956-967`
  - 问题：`lidar_online = lidar_l and lidar_r`，非双雷达配置永远 `rear_conflict` 阻塞全部自动变道；214baad1 承诺的 fallback 无提交声明撤回。
  - 需求：214baad1 "fall back to legacy BSD blind-spot gating when amapNavi stale or rear sensors never seen"。
  - 修复：amapNavi 超时/从未见后向传感器 → 回退 BSD 门控，而非永久阻塞。
  - 落地：`rear_gate.evaluate_rear_gate / evaluate_lane_change_abort` 新增 `rear_sensor_seen` 参数——传感器**从未上线**（desire_helper 以 `amapNavi.leftDevice/rightDevice` bit0 锁存）→ 回退 BSD 门控（放行不播报，方向防护由 evaluate_bsm_gate 承担）；**曾上线后失效** → 保持 fail-safe 阻断+播报；`RearRadarEnable=0`（未装雷达）行为不变。触发段与执行段（laneChangeStarting）语义一致，消除"触发放行、执行中止"矛盾。

- [ ] **P0-5 (Standards) 15 个测试文件 `import unittest` + 自建 runner（TID251 红线）**
  - 位置：`selfdrive/carrot/tests/`（15 文件）、`run_all_tdd_tests.py`
  - 标准：AGENTS.md "Use pytest for all test execution"；`pyproject.toml` TID251。
  - 修复：改为 pytest 风格（`def test_*` + 断言），删除自建 runner，统一 `pytest` 入口。

## P1 — 正确性问题

- [ ] **P1-1 (Standards) 4 空格缩进测试文件**
  - 文件：`test_atc_state_telemetry.py`、`test_c3_cooperative_modifications.py`、`test_amap_navi_networking.py`、`test_ttc_and_lane_change_gating.py`
  - 修复：`ruff format` 统一 2 空格（`.editorconfig indent_size = 2`）。

- [ ] **P1-2 (Standards) `carrot_man.py:885,887` 行长 169/162 > 160**
  - 修复：拆分两处 `json.dumps(...)` echo_cmd 错误回复。

- [ ] **P1-3 (Standards) `desire_helper.py` 控制循环内新增 `print`**
  - 修复：改 `cloudlog.info`（AGENTS.md：控制循环禁止阻塞 I/O）。

- [ ] **P1-4 (Spec) 测试抄写生产逻辑并复现 falsy-0 bug**
  - 位置：`test_c3_cooperative_modifications.py`（`json_obj.get("index") or json_obj.get("seq")`）、`test_security_switches.py:handle_echo_cmd_logic`
  - 修复：导入生产函数断言，而非复抄副本。

- [ ] **P1-5 (Spec) TTC 测试与生产语义分叉**
  - 问题：测试 helper 在 `ttc_list` 空时返回 `99.0`，生产返回 `0.0`；分叉分支无覆盖。
  - 修复：测试调用生产逻辑；补 `no_rear_target=False` 用例。

- [ ] **P1-6 (Spec) `test_atc_state_telemetry.py` 对不存在的 `MockStateMachine` 断言**
  - 修复：改为对真实 StateMachine（或删除该测试）。

## P2 — 质量 / 仓库卫生

- [ ] **P2-1 (Standards) TTC 阈值映射重复 3 处**
  - `{0: 1.8, 1: 2.5, 2: 3.5}.get(mode, 2.5)`：`desire_helper.py` ×2 + `amap_navi.make_navi_message`。→ 抽共享常量/helper。

- [ ] **P2-2 (Standards) `except (KeyError, RuntimeError, Exception)`**
  - `amap_navi._clean_clients_thread`：`Exception` 吞掉其余。→ 只留预期异常。

- [ ] **P2-3 (Standards) `app_ip` 信任 30s 后 fail open**
  - 第三方 IP 超时后被接受，测试固化了该行为。→ 超时后拒绝（fail closed），同步改测试。

- [ ] **P2-4 (Standards) 坏味道打包**
  - Data Clumps：`app_ip` + `app_ip_ts` + `30.0` → 信任窗口小类型。
  - Divergent Change：`desire_helper.py` 一次改 5 个不相关原因 → 后续按关注点拆分提交。
  - Shotging：后向 TTC fail-safe 扇出 4 文件 4 测试 → 集中到单一模块。

- [ ] **P2-5 (Spec) 范围蔓延清理**
  - `custo_manual.pdf`（43MB 二进制）、`.arts/*`、`.vscode/settings.json`、`.agnes/COMPREHENSIVE_OPTIMIZATION_PLAN.md`、`tools/*.bat`：确认去留（建议大二进制移出 git 历史）。
  - `web_interface.py` 仅绑 127.0.0.1：确认是否保留（改变了文档所述 LAN 访问行为），同步更新文档。
  - `desire_helper.py` `atc_cancel_delay` min→max：在提交信息中补说明。
